"""Copy landed parquet into the warehouse raw schema (the local stand-in for S3 -> Snowflake COPY INTO).

--until loads only rows whose _loaded_at is at or before that timestamp, so the pipeline can be
run as two batches and the incremental models proven against a full refresh.
"""
import argparse
from pathlib import Path

import duckdb


def load(db: str, data: str = "data", until: str | None = None) -> None:
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(db)
    con.execute("create schema if not exists raw")
    con.execute("create schema if not exists truth")
    for f in sorted(Path(data, "landing").glob("*.parquet")):
        where = f"where _loaded_at <= timestamp '{until}'" if until else ""
        con.execute(f"create or replace table raw.{f.stem} as select * from read_parquet('{f.as_posix()}') {where}")
    truth = Path(data, "truth", "merchant_monthly.parquet").as_posix()
    con.execute(f"create or replace table truth.merchant_monthly as select * from read_parquet('{truth}')")
    con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="warehouse/dev.duckdb")
    ap.add_argument("--data", default="data")
    ap.add_argument("--until", default=None)
    a = ap.parse_args()
    load(a.db, a.data, a.until)
