"""Break the raw feeds on purpose, one defect at a time, and prove the build catches each one.

For every defect: reload clean raw data into a scratch warehouse, apply the defect, run
`dbt build`, and record which tests failed. A defect counts as caught only if at least one
test fails. Results go to reports/defects.md.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from load_raw import load  # noqa: E402

DB = ROOT / "warehouse" / "defect.duckdb"
TARGET_PATH = "target_defect"

DEFECTS = [
    ("Payments feed stops loading 3 days before the others",
     "delete from raw.payment_transactions where _loaded_at > timestamp '2025-12-28 23:59:59'"),
    ("Payments platform switches 1 week of amounts from minor to major units",
     "update raw.payment_transactions set amount_minor = cast(amount_minor / 100 as bigint) "
     "where created_at >= timestamp '2025-12-20'"),
    ("Webhook replay re-sends 3 sales under new event_ids",
     "insert into raw.contract_events select * replace ('evt_replay_' || event_id as event_id) "
     "from raw.contract_events where event_type = 'contract.created' order by event_id limit 3"),
    ("Integration sends 5 plans with a negative price",
     "update raw.contract_events set plan_price = -plan_price where event_id in ("
     "select event_id from raw.contract_events where event_type = 'contract.created' order by event_id limit 5)"),
    ("Claims system files a claim against a contract that does not exist",
     "insert into raw.claim_status_history values ('cs_x1', 'cl_x1', 'c_9999999', 'filed', null, null, 'USD', "
     "timestamp '2025-12-30 10:00:00', timestamp '2025-12-30 10:05:00')"),
    ("Merchant CDC emits two different revenue shares at the same instant",
     "insert into raw.merchant_changes select merchant_id, 'update', merchant_name, vertical, platform, currency, "
     "0.35, is_test, changed_at, _loaded_at from raw.merchant_changes where op = 'update' order by merchant_id limit 1"),
    ("Admin enters a revenue share as a percent (25) instead of a fraction",
     "insert into raw.merchant_changes select merchant_id, 'update', merchant_name, vertical, platform, currency, "
     "25, is_test, timestamp '2025-06-01 09:00:00', timestamp '2025-06-01 09:10:00' "
     "from raw.merchant_changes where merchant_id = 'm_001' and op = 'insert'"),
    ("FX feed misses GBP for one trading day",
     "delete from raw.fx_rates where currency = 'GBP' and rate_date = date '2025-11-28'"),
    ("Cancellation service refunds 3 prorated cancels in full",
     "update raw.contract_events set refund_amount = plan_price where event_id in ("
     "select event_id from raw.contract_events where event_type = 'contract.cancelled' "
     "and refund_amount < plan_price * 0.8 order by event_id limit 3)"),
]


def dbt_exe() -> str:
    scripts = Path(sys.executable).parent
    for name in ("dbt.exe", "dbt"):
        if (scripts / name).exists():
            return str(scripts / name)
    return "dbt"


def run_defect(sql: str) -> list[str]:
    load(str(DB), str(ROOT / "data"))
    con = duckdb.connect(str(DB))
    con.execute(sql)
    con.close()
    subprocess.run([dbt_exe(), "build", "--target", "defect", "--full-refresh", "--target-path", TARGET_PATH],
                   cwd=ROOT, capture_output=True, text=True, env={**__import__("os").environ, "DBT_PROFILES_DIR": str(ROOT)})
    results = json.loads((ROOT / TARGET_PATH / "run_results.json").read_text())["results"]
    failed = []
    for r in results:
        if r["status"] in ("fail", "error"):
            failed.append(r["unique_id"].split(".")[2])
    return failed


def main() -> int:
    rows, caught = [], 0
    for name, sql in DEFECTS:
        failed = run_defect(sql)
        ok = bool(failed)
        caught += ok
        print(f"{'CAUGHT' if ok else 'MISSED'}  {name}  ->  {', '.join(failed) or 'nothing failed'}")
        rows.append((name, failed))
    out = ROOT / "reports" / "defects.md"
    out.parent.mkdir(exist_ok=True)
    lines = [f"# Injected defects: {caught} of {len(DEFECTS)} caught\n",
             "Each defect is applied alone to clean raw data, then `dbt build` runs.\n",
             "| Defect | Caught by |", "|---|---|"]
    for name, failed in rows:
        lines.append(f"| {name} | {', '.join(f'`{f}`' for f in failed) or '**missed**'} |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n{caught} of {len(DEFECTS)} defects caught")
    return 0 if caught == len(DEFECTS) else 1


if __name__ == "__main__":
    sys.exit(main())
