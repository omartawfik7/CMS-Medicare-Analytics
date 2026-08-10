"""Smoke tests for the Bronze -> Silver -> Gold pipeline, run against the
committed real CMS sample so they don't depend on any external download."""

import subprocess
import sys
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_CSV = REPO_ROOT / "data" / "raw" / "sample_mup_phy_provider_service_2023.csv"


def test_bronze_ingestion(tmp_path):
    db_path = tmp_path / "test.duckdb"
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "src" / "ingestion.py"),
            "--csv", str(SAMPLE_CSV),
            "--year", "2023",
            "--vintage", "test",
            "--db", str(db_path),
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert db_path.exists()

    con = duckdb.connect(str(db_path))
    row_count = con.execute("SELECT COUNT(*) FROM bronze_physician_service").fetchone()[0]
    assert row_count == 37
    con.close()


def test_silver_and_gold(tmp_path):
    db_path = tmp_path / "test.duckdb"
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "src" / "ingestion.py"),
            "--csv", str(SAMPLE_CSV),
            "--year", "2023",
            "--vintage", "test",
            "--db", str(db_path),
        ],
        check=True,
    )

    con = duckdb.connect(str(db_path))
    con.execute((REPO_ROOT / "sql" / "silver" / "silver_physician_service.sql").read_text())
    con.execute((REPO_ROOT / "sql" / "gold" / "gold_provider_performance.sql").read_text())

    silver_rows = con.execute("SELECT COUNT(*) FROM silver_physician_service").fetchone()[0]
    assert silver_rows == 37

    gold_rows = con.execute("SELECT COUNT(*) FROM gold_provider_performance").fetchone()[0]
    assert gold_rows == 12  # 12 distinct providers in the sample

    # Every provider's total payment should be positive and finite.
    bad = con.execute(
        "SELECT COUNT(*) FROM gold_provider_performance "
        "WHERE provider_total_medicare_payment IS NULL OR provider_total_medicare_payment <= 0"
    ).fetchone()[0]
    assert bad == 0

    con.close()
