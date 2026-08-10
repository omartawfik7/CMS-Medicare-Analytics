"""
Bronze-layer ingestion for the CMS Medicare Physician & Other Practitioners
"by Provider and Service" public use file (MUP_PHY_*_Prov_Svc.csv).

Design goals
------------
- Same code path for a single-year sample and the full national file(s) --
  scaling from MVP to production is a matter of pointing SOURCE_FILES at
  more/larger CSVs, not rewriting the pipeline.
- Bronze = raw grain, raw types (mostly VARCHAR), + ingestion metadata.
  No cleaning, no renaming, no type coercion beyond what's needed to load.
  Cleaning/typing happens in Silver (sql/silver/).
- Idempotent: re-running for the same (source_year, source_file) replaces
  that slice rather than duplicating it.

Data source
-----------
CMS data.cms.gov, dataset "Medicare Physician & Other Practitioners -
by Provider and Service". Official API (per-year UUIDs) and flat-file CSV
downloads are both published; see data/README.md for the full list of
confirmed URLs by year, and config/cms_sources.yaml for the machine-readable
version used here.

Network note
------------
This script expects the source CSV(s) to already be on local disk under
data/raw/ (see data/README.md for exact download commands). It does not
reach out to data.cms.gov itself, so it works the same whether the file
came from a manual `curl`, a scheduled download job, or (for schema
validation only) a small API-pulled sample.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import duckdb

# Canonical Bronze column order/types, taken verbatim from the live CMS API
# response (data-api/v1/dataset/92396110-2aed-4d63-a6a2-5d6207d46a29/data),
# confirmed 2026-08-10. All source columns are loaded as VARCHAR in Bronze;
# CMS ships numeric fields as strings in the API/CSV and mixes suppressed
# ("*") values into otherwise-numeric columns, so casting happens in Silver
# after suppression handling.
BRONZE_COLUMNS = [
    "Rndrng_NPI",
    "Rndrng_Prvdr_Last_Org_Name",
    "Rndrng_Prvdr_First_Name",
    "Rndrng_Prvdr_MI",
    "Rndrng_Prvdr_Crdntls",
    "Rndrng_Prvdr_Ent_Cd",
    "Rndrng_Prvdr_St1",
    "Rndrng_Prvdr_St2",
    "Rndrng_Prvdr_City",
    "Rndrng_Prvdr_State_Abrvtn",
    "Rndrng_Prvdr_State_FIPS",
    "Rndrng_Prvdr_Zip5",
    "Rndrng_Prvdr_RUCA",
    "Rndrng_Prvdr_RUCA_Desc",
    "Rndrng_Prvdr_Cntry",
    "Rndrng_Prvdr_Type",
    "Rndrng_Prvdr_Mdcr_Prtcptg_Ind",
    "HCPCS_Cd",
    "HCPCS_Desc",
    "HCPCS_Drug_Ind",
    "Place_Of_Srvc",
    "Tot_Benes",
    "Tot_Srvcs",
    "Tot_Bene_Day_Srvcs",
    "Avg_Sbmtd_Chrg",
    "Avg_Mdcr_Alowd_Amt",
    "Avg_Mdcr_Pymt_Amt",
    "Avg_Mdcr_Stdzd_Amt",
]


@dataclass
class SourceFile:
    path: Path
    source_year: int  # calendar year the utilization data covers
    vintage: str  # CMS release label, e.g. "R25_P05_V20_D23" (informational)


def load_bronze(
    con: duckdb.DuckDBPyConnection,
    source: SourceFile,
    table_name: str = "bronze_physician_service",
) -> dict:
    """Load one CMS CSV into the Bronze table, replacing any existing rows
    for that source_year + source_file so re-runs are idempotent."""

    t0 = time.time()

    col_list_sql = ", ".join(f'"{c}"' for c in BRONZE_COLUMNS)

    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            {", ".join(f'"{c}" VARCHAR' for c in BRONZE_COLUMNS)},
            source_year INTEGER,
            source_file VARCHAR,
            source_vintage VARCHAR,
            ingested_at TIMESTAMP
        )
    """)

    # Idempotency: clear any prior load of this exact source before inserting.
    con.execute(
        f"DELETE FROM {table_name} WHERE source_file = ?",
        [str(source.path.name)],
    )

    con.execute(f"""
        INSERT INTO {table_name}
        SELECT {col_list_sql},
               {source.source_year} AS source_year,
               '{source.path.name}' AS source_file,
               '{source.vintage}' AS source_vintage,
               now() AS ingested_at
        FROM read_csv(
            '{source.path.as_posix()}',
            header = true,
            all_varchar = true,
            sample_size = -1
        )
    """)

    elapsed = time.time() - t0
    row_count = con.execute(
        f"SELECT COUNT(*) FROM {table_name} WHERE source_file = ?",
        [str(source.path.name)],
    ).fetchone()[0]

    return {
        "source_file": source.path.name,
        "source_year": source.source_year,
        "rows_loaded": row_count,
        "elapsed_seconds": round(elapsed, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Load CMS Physician & Other Practitioners CSV(s) into DuckDB Bronze.")
    parser.add_argument("--db", default="data/cms_medicare.duckdb", help="Path to the DuckDB database file.")
    parser.add_argument("--csv", required=True, help="Path to a source CSV file.")
    parser.add_argument("--year", type=int, required=True, help="Calendar year the file covers (e.g. 2023).")
    parser.add_argument("--vintage", default="unknown", help="CMS release/vintage label for provenance.")
    args = parser.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db_path))
    source = SourceFile(path=Path(args.csv), source_year=args.year, vintage=args.vintage)
    stats = load_bronze(con, source)
    con.close()

    print(f"Loaded {stats['rows_loaded']:,} rows from {stats['source_file']} "
          f"(year={stats['source_year']}) in {stats['elapsed_seconds']}s "
          f"-> {db_path}")


if __name__ == "__main__":
    sys.exit(main())
