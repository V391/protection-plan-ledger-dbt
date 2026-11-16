"""Simulate two years of a post-purchase protection business and land it as raw files.

Merchants sell protection plans at checkout. Plans can be cancelled (full refund in the
30 day free look window or before coverage starts, prorated after), customers file claims,
and a payments platform settles every charge and refund. The raw feeds look the way they
arrive in a warehouse: webhook events delivered at least once, payments in minor units,
merchant settings as a CDC log, claim statuses that land late, three currencies.

Outputs
  data/landing/<table>.parquet   raw feeds, every row stamped with _loaded_at
  data/truth/merchant_monthly.parquet   the answer, computed here, independent of dbt
"""
from __future__ import annotations

import argparse
import calendar
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

START = date(2024, 1, 1)
END = date(2025, 12, 31)
END_TS = datetime(2025, 12, 31, 23, 59, 59)

# vertical: price lognormal mu, sigma, manufacturer warranty months, claim probability, plan terms
VERTICALS = {
    "electronics": (5.6, 0.7, 12, 0.06, [12, 24, 36]),
    "appliances": (6.2, 0.6, 12, 0.05, [24, 36]),
    "furniture": (6.4, 0.6, 0, 0.05, [24, 36]),
    "bikes": (6.8, 0.5, 0, 0.07, [12, 24]),
    "jewelry": (5.8, 0.9, 0, 0.03, [12, 24, 36]),
    "apparel": (4.3, 0.5, 0, 0.025, [12]),
}
TERM_PRICE_PCT = {12: 0.10, 24: 0.16, 36: 0.21}
NAME_SUFFIX = {
    "electronics": "Electronics", "appliances": "Home Appliances", "furniture": "Furniture Co",
    "bikes": "Cycles", "jewelry": "Jewelers", "apparel": "Outfitters",
}
PREFIXES = [
    "Northwind", "Bluebird", "Summit", "Harbor", "Cedar", "Lumen", "Granite", "Maple", "Orbit", "Pioneer",
    "Riverside", "Sable", "Tidewater", "Union", "Vantage", "Willow", "Aspen", "Beacon", "Copper", "Driftwood",
]
CURRENCIES = ["USD", "CAD", "GBP"]


def q2(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def add_months(d: date, n: int) -> date:
    y = d.year + (d.month - 1 + n) // 12
    m = (d.month - 1 + n) % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    out = Path(args.out)

    def ts_on(d: date) -> datetime:
        return datetime.combine(d, time()) + timedelta(seconds=int(rng.integers(0, 86400)))

    def loaded(t: datetime, lo_min=2, hi_min=90) -> datetime:
        return min(t + timedelta(minutes=float(rng.uniform(lo_min, hi_min))), END_TS)

    # ---------------- FX ----------------
    fx_rows, fx = [], {}
    level = {"USD": 1.0, "CAD": 0.73, "GBP": 1.27}
    d = date(2023, 12, 1)
    while d <= date(2026, 1, 31):
        for cur in CURRENCIES:
            if cur != "USD":
                level[cur] *= float(np.exp(rng.normal(0, 0.003)))
            rate = round(level[cur], 6)
            fx[(cur, d)] = rate
            fx_rows.append((cur, d, rate, loaded(datetime.combine(d, time(6)))))
        d += timedelta(days=1)

    # ---------------- Merchants (CDC log) ----------------
    merchants, cdc = [], []
    verticals = list(VERTICALS)
    for i in range(42):
        is_test = i >= 40
        vertical = verticals[i % len(verticals)]
        mid = f"m_{i + 1:03d}"
        name = "QA Sandbox Store" if is_test else f"{PREFIXES[i % len(PREFIXES)]} {NAME_SUFFIX[vertical]}"
        if is_test:
            name += f" {i - 39}"
        currency = "USD" if is_test else str(rng.choice(CURRENCIES, p=[0.7, 0.18, 0.12]))
        platform = str(rng.choice(["shopify", "bigcommerce", "api"], p=[0.6, 0.15, 0.25]))
        onboard = date(2023, 6, 1) + timedelta(days=int(rng.integers(0, 200))) if (i < 25 or is_test) \
            else date(2024, 1, 1) + timedelta(days=int(rng.integers(0, 330)))
        rate = float(rng.choice([0.15, 0.20, 0.25, 0.30]))
        m = dict(merchant_id=mid, name=name, vertical=vertical, platform=platform, currency=currency,
                 is_test=is_test, onboard=onboard, lam=float(rng.uniform(1.0, 5.0)),
                 attach=float(rng.uniform(0.10, 0.40)), rate_history=[])
        t0 = datetime.combine(onboard, time())  # merchant record exists before its first order
        m["rate_history"].append((t0, rate))
        cdc.append((mid, "insert", name, vertical, platform, currency, rate, is_test, t0, t0 + timedelta(minutes=10)))
        first_active = max(onboard, START)
        n_changes = int(rng.choice([0, 1, 2], p=[0.45, 0.4, 0.15]))
        window = (END - first_active).days - 60
        for _ in range(n_changes if window > 0 else 0):
            cd = first_active + timedelta(days=30 + int(rng.integers(0, window)))
            rate = float(rng.choice([0.15, 0.20, 0.25, 0.30, 0.35]))
            tc = ts_on(cd)
            m["rate_history"].append((tc, rate))
            cdc.append((mid, "update", name, vertical, platform, currency, rate, is_test, tc, tc + timedelta(minutes=10)))
        m["rate_history"].sort()
        merchants.append(m)

    def rate_at(m, t: datetime) -> float:
        r = m["rate_history"][0][1]
        for tc, rv in m["rate_history"]:
            if tc <= t:
                r = rv
        return r

    # ---------------- Orders, plans, claims, cancellations, payments ----------------
    orders, lines, events, claim_rows, payments = [], [], [], [], []
    truth = defaultdict(lambda: defaultdict(float))  # (merchant, month) -> metric -> value
    n_order = n_line = n_contract = n_claim = n_evt = n_txn = n_cs = 0

    def evt_id():
        nonlocal n_evt
        n_evt += 1
        return f"evt_{n_evt:07d}"

    def txn_id():
        nonlocal n_txn
        n_txn += 1
        return f"txn_{n_txn:07d}"

    def emit_event(row: dict):
        events.append(row)
        if rng.random() < 0.03:  # at-least-once delivery: same event_id, delivered again later
            dup = dict(row)
            dup["received_at"] = row["received_at"] + timedelta(seconds=float(rng.uniform(60, 7200)))
            dup["_loaded_at"] = min(dup["received_at"] + timedelta(minutes=10), END_TS)
            events.append(dup)

    for m in merchants:
        mu, sigma, warranty_m, claim_p, terms = VERTICALS[m["vertical"]]
        cur = m["currency"]
        d = max(m["onboard"], START)
        while d <= END:
            season = 1.6 if d.month in (11, 12) else 1.0
            for _ in range(int(rng.poisson(m["lam"] * season))):
                n_order += 1
                oid = f"o_{n_order:07d}"
                ordered_at = ts_on(d)
                order_loaded = loaded(ordered_at, 5, 60)  # lines arrive in the same order payload
                orders.append((oid, m["merchant_id"], ordered_at, cur, order_loaded))
                for _ in range(int(rng.choice([1, 2, 3], p=[0.6, 0.3, 0.1]))):
                    n_line += 1
                    lid = f"ol_{n_line:08d}"
                    price = q2(max(5.0, float(rng.lognormal(mu, sigma))))
                    eligible = price >= Decimal("40")
                    lines.append((lid, oid, f"sku_{m['vertical'][:3]}_{int(rng.integers(1, 400)):04d}",
                                  m["vertical"], float(price), eligible, order_loaded))
                    ms = month_start(d)
                    if not m["is_test"] and eligible:
                        truth[(m["merchant_id"], ms)]["eligible_lines"] += 1
                    if not (eligible and rng.random() < m["attach"]):
                        continue

                    # ---- protection plan sold ----
                    n_contract += 1
                    cid = f"c_{n_contract:07d}"
                    term = int(rng.choice(terms))
                    plan_price = max(q2(float(price) * TERM_PRICE_PCT[term]), Decimal("4.99"))
                    purchased_at = ordered_at + timedelta(seconds=float(rng.uniform(1, 30)))
                    pdate = purchased_at.date()
                    cov_start = add_months(pdate, warranty_m)
                    cov_end = add_months(cov_start, term)
                    share = rate_at(m, purchased_at)
                    fx_p = fx[(cur, pdate)]
                    recv = purchased_at + timedelta(seconds=float(rng.uniform(1, 30)))
                    emit_event(dict(
                        event_id=evt_id(), event_type="contract.created", contract_id=cid, merchant_id=m["merchant_id"],
                        order_line_id=lid, product_category=m["vertical"], plan_term_months=term,
                        plan_price=float(plan_price), currency=cur, coverage_start_date=cov_start,
                        coverage_end_date=cov_end, refund_amount=None, occurred_at=purchased_at, received_at=recv,
                        _loaded_at=min(recv + timedelta(minutes=float(rng.uniform(5, 60))), END_TS)))
                    t_charge = purchased_at + timedelta(seconds=float(rng.uniform(1, 20)))
                    amt_minor = int(plan_price * 100)
                    payments.append((txn_id(), "charge", cid, m["merchant_id"], cur, amt_minor,
                                     int(round(amt_minor * 0.029 + 30)), t_charge, loaded(t_charge, 30, 180)))

                    key = (m["merchant_id"], month_start(pdate))
                    if not m["is_test"]:
                        t = truth[key]
                        t["contracts_sold"] += 1
                        t["gwp_usd"] += float(plan_price) * fx_p
                        t["merchant_payable_usd"] += float(plan_price) * fx_p * share

                    # ---- claim (contracts with a claim are never cancelled) ----
                    has_claim = False
                    claim_hi = min(cov_end, END)
                    if cov_start < claim_hi and rng.random() < claim_p:
                        has_claim = True
                        n_claim += 1
                        clid = f"cl_{n_claim:06d}"
                        filed = ts_on(cov_start + timedelta(days=int(rng.integers(0, (claim_hi - cov_start).days))))
                        steps = [("filed", filed, None, None)]
                        review = filed + timedelta(days=float(rng.uniform(0.5, 3)))
                        steps.append(("in_review", review, None, None))
                        decided = review + timedelta(days=float(rng.uniform(1, 10)))
                        if rng.random() < 0.8:
                            res = str(rng.choice(["repair", "replace", "refund"], p=[0.5, 0.35, 0.15]))
                            pct = {"repair": rng.uniform(0.15, 0.45), "replace": rng.uniform(0.85, 1.0), "refund": 1.0}[res]
                            amount = q2(float(price) * float(pct))
                            steps.append(("approved", decided, res, amount))
                            paid = decided + timedelta(days=float(rng.uniform(1, 7)))
                            steps.append(("paid", paid, res, amount))
                        else:
                            steps.append(("denied", decided, None, None))
                        late = rng.random() < 0.04
                        for status, t_s, res, amount in steps:
                            if t_s > END_TS:
                                break
                            n_cs += 1
                            lag = timedelta(days=float(rng.uniform(2, 9))) if late else timedelta(minutes=float(rng.uniform(2, 90)))
                            claim_rows.append((f"cs_{n_cs:07d}", clid, cid, status, res,
                                               float(amount) if amount is not None else None, cur, t_s, min(t_s + lag, END_TS)))
                            if status == "paid" and not m["is_test"]:
                                truth[(m["merchant_id"], month_start(t_s.date()))]["claims_paid_usd"] += \
                                    float(amount) * fx[(cur, t_s.date())]

                    # ---- cancellation ----
                    cancel_date = None
                    if not has_claim and rng.random() < 0.07:
                        if rng.random() < 0.4:
                            cancel_date = pdate + timedelta(days=int(rng.integers(1, 30)))
                        else:
                            span = (min(cov_end, END) - pdate).days - 30
                            if span > 0:
                                cancel_date = pdate + timedelta(days=30 + int(rng.integers(0, span)))
                        if cancel_date is not None and (cancel_date > END or cancel_date >= cov_end):
                            cancel_date = None
                    refund = Decimal("0")
                    if cancel_date is not None:
                        if (cancel_date - pdate).days < 30 or cancel_date <= cov_start:
                            refund = plan_price
                        else:
                            frac = (cov_end - cancel_date).days / (cov_end - cov_start).days
                            refund = q2(float(plan_price) * frac)
                        cancelled_at = ts_on(cancel_date)
                        recv = cancelled_at + timedelta(seconds=float(rng.uniform(1, 30)))
                        emit_event(dict(
                            event_id=evt_id(), event_type="contract.cancelled", contract_id=cid,
                            merchant_id=m["merchant_id"], order_line_id=lid, product_category=m["vertical"],
                            plan_term_months=term, plan_price=float(plan_price), currency=cur,
                            coverage_start_date=cov_start, coverage_end_date=cov_end, refund_amount=float(refund),
                            occurred_at=cancelled_at, received_at=recv,
                            _loaded_at=min(recv + timedelta(minutes=float(rng.uniform(5, 60))), END_TS)))
                        t_ref = cancelled_at + timedelta(seconds=float(rng.uniform(1, 20)))
                        payments.append((txn_id(), "refund", cid, m["merchant_id"], cur, -int(refund * 100), 0,
                                         t_ref, loaded(t_ref, 30, 180)))
                        if not m["is_test"]:
                            t = truth[(m["merchant_id"], month_start(cancel_date))]
                            t["refunds_usd"] += float(refund) * fx_p
                            t["merchant_payable_usd"] -= float(refund) * fx_p * share

                    # ---- earned revenue: net price spread evenly over the days actually covered ----
                    if not m["is_test"]:
                        net_usd = float(plan_price - refund) * fx_p
                        earn_end = cov_end if cancel_date is None else (cov_start if refund == plan_price else cancel_date)
                        days_total = (earn_end - cov_start).days
                        if net_usd > 0 and days_total > 0:
                            cur_m = month_start(cov_start)
                            horizon_end = END + timedelta(days=1)
                            while cur_m < min(earn_end, horizon_end):
                                nxt = add_months(cur_m, 1)
                                days = (min(earn_end, nxt, horizon_end) - max(cov_start, cur_m)).days
                                if days > 0:
                                    truth[(m["merchant_id"], cur_m)]["earned_usd"] += net_usd * days / days_total
                                cur_m = nxt
            d += timedelta(days=1)

    # ---------------- Write ----------------
    land = out / "landing"
    land.mkdir(parents=True, exist_ok=True)
    (out / "truth").mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()

    def write(df: pd.DataFrame, path: Path):
        con.register("df", df)
        con.execute(f"copy df to '{path.as_posix()}' (format parquet)")
        con.unregister("df")

    write(pd.DataFrame(fx_rows, columns=["currency", "rate_date", "usd_per_unit", "_loaded_at"]), land / "fx_rates.parquet")
    write(pd.DataFrame(cdc, columns=["merchant_id", "op", "merchant_name", "vertical", "platform", "currency",
                                     "revenue_share_rate", "is_test", "changed_at", "_loaded_at"]), land / "merchant_changes.parquet")
    write(pd.DataFrame(orders, columns=["order_id", "merchant_id", "ordered_at", "currency", "_loaded_at"]), land / "orders.parquet")
    write(pd.DataFrame(lines, columns=["order_line_id", "order_id", "sku", "product_category", "unit_price",
                                       "is_eligible", "_loaded_at"]), land / "order_lines.parquet")
    ev = pd.DataFrame(events)
    for c in ("coverage_start_date", "coverage_end_date"):
        ev[c] = pd.to_datetime(ev[c])
    write(ev, land / "contract_events.parquet")
    write(pd.DataFrame(claim_rows, columns=["claim_status_id", "claim_id", "contract_id", "status", "resolution",
                                            "amount", "currency", "changed_at", "_loaded_at"]), land / "claim_status_history.parquet")
    write(pd.DataFrame(payments, columns=["txn_id", "txn_type", "contract_id", "merchant_id", "currency", "amount_minor",
                                          "fee_minor", "created_at", "_loaded_at"]), land / "payment_transactions.parquet")

    metrics = ["eligible_lines", "contracts_sold", "gwp_usd", "refunds_usd", "earned_usd", "claims_paid_usd", "merchant_payable_usd"]
    t_rows = [(mid, ms, *[truth[(mid, ms)].get(k, 0.0) for k in metrics]) for (mid, ms) in sorted(truth)]
    tdf = pd.DataFrame(t_rows, columns=["merchant_id", "month_start", *metrics])
    tdf["month_start"] = pd.to_datetime(tdf["month_start"])
    write(tdf, out / "truth" / "merchant_monthly.parquet")

    n_dupes = len(ev) - ev["event_id"].nunique()
    print(f"merchants {len(merchants)} (2 test) | orders {len(orders):,} | lines {len(lines):,} | contracts {n_contract:,} | "
          f"claims {n_claim:,} | events {len(ev):,} ({n_dupes} redelivered) | payment txns {len(payments):,}")


if __name__ == "__main__":
    main()
