"""
Apply every SQL script under sql/gold/ to the DuckDB warehouse, in filename
order (numeric prefixes control dependency order -- provider_year before
specialty_year, benchmark before outlier, etc). Run after build_silver.py.

    python src/build_gold.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLD_DIR = REPO_ROOT / "sql" / "gold"

SUMMARY_TABLES = [
    "gold_provider_year",
    "gold_specialty_year",
    "gold_state_year",
    "gold_procedure_year",
    "gold_provider_benchmark",
    "gold_provider_outlier",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Gold-layer analytics tables from Silver.")
    parser.add_argument("--db", default=str(REPO_ROOT / "data" / "cms_medicare.duckdb"))
    args = parser.parse_args()

    con = duckdb.connect(args.db)
    sql_files = sorted(GOLD_DIR.glob("*.sql"))
    if not sql_files:
        print(f"No SQL files found in {GOLD_DIR}", file=sys.stderr)
        sys.exit(1)

    for sql_file in sql_files:
        t0 = time.time()
        con.execute(sql_file.read_text())
        print(f"ran {sql_file.relative_to(REPO_ROOT)} in {time.time() - t0:.1f}s")

    print()
    for table in SUMMARY_TABLES:
        exists = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [table]
        ).fetchone()[0]
        if exists:
            n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"{table}: {n:,} rows")
    con.close()


if __name__ == "__main__":
    sys.exit(main())
