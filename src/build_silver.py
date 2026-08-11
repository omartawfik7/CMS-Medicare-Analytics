"""
Apply every SQL script under sql/silver/ to the DuckDB warehouse, in
filename order. Run after src/ingest_cms.py has loaded one or more years
into Bronze.

    python src/build_silver.py
    python src/build_silver.py --db data/cms_medicare.duckdb
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[1]
SILVER_DIR = REPO_ROOT / "sql" / "silver"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Silver-layer tables from Bronze.")
    parser.add_argument("--db", default=str(REPO_ROOT / "data" / "cms_medicare.duckdb"))
    args = parser.parse_args()

    con = duckdb.connect(args.db)
    sql_files = sorted(SILVER_DIR.glob("*.sql"))
    if not sql_files:
        print(f"No SQL files found in {SILVER_DIR}", file=sys.stderr)
        sys.exit(1)

    for sql_file in sql_files:
        t0 = time.time()
        con.execute(sql_file.read_text())
        print(f"ran {sql_file.relative_to(REPO_ROOT)} in {time.time() - t0:.1f}s")

    row_count = con.execute("SELECT COUNT(*) FROM silver_physician_service").fetchone()[0]
    years = con.execute("SELECT DISTINCT source_year FROM silver_physician_service ORDER BY 1").fetchall()
    print(f"silver_physician_service: {row_count:,} rows across years {[y[0] for y in years]}")
    con.close()


if __name__ == "__main__":
    sys.exit(main())
