"""End to end: generate, build in two incremental batches, prove incremental == full refresh,
reconcile against the answer key, inject defects, check docs, write reports/results.md."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import duckdb

from load_raw import load

ROOT = Path(__file__).resolve().parent
ENV = {**os.environ, "DBT_PROFILES_DIR": str(ROOT)}
BATCH_1_CUTOFF = "2025-11-01 00:00:00"


def dbt(*args: str) -> None:
    scripts = Path(sys.executable).parent
    exe = next((str(scripts / n) for n in ("dbt.exe", "dbt") if (scripts / n).exists()), "dbt")
    print(f"$ dbt {' '.join(args)}", flush=True)
    r = subprocess.run([exe, *args], cwd=ROOT, env=ENV, capture_output=True, text=True)
    tail = [l for l in r.stdout.splitlines() if "Done." in l or "FAIL" in l or "ERROR" in l]
    print("  " + "\n  ".join(tail[-6:]))
    if r.returncode:
        print(r.stdout[-4000:])
        sys.exit(r.returncode)


def py(*args: str) -> None:
    r = subprocess.run([sys.executable, *args], cwd=ROOT, env=ENV)
    if r.returncode:
        sys.exit(r.returncode)


def compare_incremental_to_full() -> dict[str, int]:
    con = duckdb.connect(str(ROOT / "warehouse" / "dev.duckdb"))
    con.execute(f"attach '{(ROOT / 'warehouse' / 'full.duckdb').as_posix()}' as full_db (read_only)")
    keys = {
        "fct_contracts": ["contract_id"],
        "fct_contract_earnings_monthly": ["contract_id", "month_start"],
        "fct_claims": ["claim_id"],
        "mrt_merchant_monthly": ["merchant_id", "month_start"],
    }
    diffs = {}
    for table, key in keys.items():
        cols = con.execute(
            "select column_name, data_type from information_schema.columns "
            f"where table_catalog = 'dev' and table_schema = 'marts' and table_name = '{table}' order by ordinal_position"
        ).fetchall()
        # Doubles may differ in the last bits from summation order: compare them within 1e-6.
        # Everything else must be identical. A row missing on either side counts as a difference.
        conds = [f"a.{c} is distinct from b.{c}" for c, t in cols if t != "DOUBLE" and c not in key]
        conds += [f"coalesce(abs(a.{c} - b.{c}) > 1e-6, (a.{c} is null) <> (b.{c} is null))" for c, t in cols if t == "DOUBLE"]
        on = " and ".join(f"a.{k} = b.{k}" for k in key)
        missing = " or ".join(f"a.{k} is null or b.{k} is null" for k in key)
        n = con.execute(
            f"select count(*) from dev.marts.{table} a full outer join full_db.marts.{table} b on {on} "
            f"where {missing} or {' or '.join(conds)}"
        ).fetchone()[0]
        diffs[table] = n
    con.close()
    return diffs


def headline() -> dict:
    con = duckdb.connect(str(ROOT / "warehouse" / "full.duckdb"), read_only=True)
    q = lambda s: con.execute(s).fetchone()  # noqa: E731
    h = {}
    h["contracts"], h["gwp"], h["refunds"], h["earned"], h["claims_paid"], h["payable"] = q(
        "select sum(contracts_sold), sum(gwp_usd), sum(refunds_usd), sum(earned_usd), sum(claims_paid_usd), "
        "sum(merchant_payable_usd) from marts.mrt_merchant_monthly")
    h["attach"] = q("select sum(contracts_sold) * 1.0 / sum(eligible_lines) from marts.mrt_merchant_monthly")[0]
    h["merchant_months"] = q("select count(*) from marts.mrt_merchant_monthly")[0]
    h["rec_rows"], h["rec_matched"], h["rec_in_flight"] = q(
        "select count(*), count(*) filter (where match_status = 'matched'), "
        "count(*) filter (where match_status = 'in_flight') from marts.rec_contract_payments")
    h["redelivered"] = q("select count(*) - count(distinct event_id) from raw.contract_events")[0]
    h["late_claim_rows"] = q(
        "select count(*) from raw.claim_status_history where _loaded_at > changed_at + interval 1 day")[0]
    h["share_changes"] = q("select count(*) from raw.merchant_changes where op = 'update'")[0]
    h["deferred"] = h["gwp"] - h["refunds"] - h["earned"]
    con.close()
    return h


def main() -> None:
    py("generator/generate.py")

    print("\n== Batch 1: data loaded up to", BATCH_1_CUTOFF)
    load(str(ROOT / "warehouse" / "dev.duckdb"), str(ROOT / "data"), BATCH_1_CUTOFF)
    dbt("build", "--target", "dev", "--full-refresh", "--exclude", "tag:truth")

    print("\n== Batch 2: the rest lands, incremental run")
    load(str(ROOT / "warehouse" / "dev.duckdb"), str(ROOT / "data"))
    dbt("build", "--target", "dev")

    print("\n== Full refresh from scratch, for comparison")
    load(str(ROOT / "warehouse" / "full.duckdb"), str(ROOT / "data"))
    dbt("build", "--target", "full", "--full-refresh")
    py("checks/check_docs.py")

    diffs = compare_incremental_to_full()
    print("\nIncremental vs full refresh, rows that differ:", diffs)
    if any(diffs.values()):
        sys.exit("Incremental build drifted from full refresh")

    print("\n== Injected defects")
    py("checks/inject_defects.py")

    h = headline()
    defects = (ROOT / "reports" / "defects.md").read_text(encoding="utf-8").splitlines()[0].lstrip("# ")
    report = f"""# Results

Simulation: 40 merchants (plus 2 sandbox stores), Jan 2024 to Dec 2025, USD, CAD and GBP.

| Metric | Value |
|---|---|
| Protection plans sold | {h['contracts']:,} |
| Attach rate on eligible lines | {h['attach']:.1%} |
| Gross written premium | ${h['gwp']:,.0f} |
| Refunds on cancellations | ${h['refunds']:,.0f} |
| Earned revenue | ${h['earned']:,.0f} |
| Deferred (unearned) at Dec 2025 | ${h['deferred']:,.0f} |
| Claims paid | ${h['claims_paid']:,.0f} |
| Loss ratio (claims paid / earned) | {h['claims_paid'] / h['earned']:.1%} |
| Merchant revenue share payable | ${h['payable']:,.0f} |

## Proof

- **Answer key:** `mrt_merchant_monthly` matches the simulator's independent answer key on all {h['merchant_months']:,} merchant months, 7 metrics each, counts exact and money to the cent.
- **Finance reconciliation:** {h['rec_matched']:,} of {h['rec_rows']:,} ledger and payment movements matched to the cent; {h['rec_in_flight']} in flight at the cutoff; 0 breaks.
- **Incremental == full refresh:** built in two batches (cutoff {BATCH_1_CUTOFF}), then compared with a from-scratch build: 0 differing rows across {', '.join(diffs)}.
- **Traps handled:** {h['redelivered']:,} redelivered webhook events, {h['late_claim_rows']} claim status rows landing over a day late, {h['share_changes']} mid-stream revenue share changes, payments in minor units, 3 currencies, 2 sandbox stores.
- **{defects}**: see [defects.md](defects.md).
"""
    (ROOT / "reports" / "results.md").write_text(report, encoding="utf-8")
    print("\n" + report)


if __name__ == "__main__":
    main()
