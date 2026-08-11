"""
Export Gold-layer DuckDB tables to a star schema of Parquet files for the
Power BI semantic model (powerbi/*.SemanticModel).

Dimension tables get surrogate-free natural keys (NPI, HCPCS code, state
abbreviation, specialty label, year) -- no need for surrogate integer keys
at this scale, and natural keys keep the DAX/M layer easy to audit against
the DuckDB source of truth.

    python src/export_gold_for_powerbi.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "powerbi" / "data"

# Census region/division lookup -- the only static reference data this
# project adds that isn't in the CMS file itself, used purely for the
# Geographic Intelligence page's region rollups.
STATE_REGION_SQL = """
CREATE OR REPLACE TEMP TABLE state_region AS
SELECT * FROM (VALUES
 ('CT','Connecticut','Northeast','New England'),('ME','Maine','Northeast','New England'),('MA','Massachusetts','Northeast','New England'),
 ('NH','New Hampshire','Northeast','New England'),('RI','Rhode Island','Northeast','New England'),('VT','Vermont','Northeast','New England'),
 ('NJ','New Jersey','Northeast','Middle Atlantic'),('NY','New York','Northeast','Middle Atlantic'),('PA','Pennsylvania','Northeast','Middle Atlantic'),
 ('IL','Illinois','Midwest','East North Central'),('IN','Indiana','Midwest','East North Central'),('MI','Michigan','Midwest','East North Central'),
 ('OH','Ohio','Midwest','East North Central'),('WI','Wisconsin','Midwest','East North Central'),
 ('IA','Iowa','Midwest','West North Central'),('KS','Kansas','Midwest','West North Central'),('MN','Minnesota','Midwest','West North Central'),
 ('MO','Missouri','Midwest','West North Central'),('NE','Nebraska','Midwest','West North Central'),('ND','North Dakota','Midwest','West North Central'),
 ('SD','South Dakota','Midwest','West North Central'),
 ('DE','Delaware','South','South Atlantic'),('FL','Florida','South','South Atlantic'),('GA','Georgia','South','South Atlantic'),
 ('MD','Maryland','South','South Atlantic'),('NC','North Carolina','South','South Atlantic'),('SC','South Carolina','South','South Atlantic'),
 ('VA','Virginia','South','South Atlantic'),('DC','District of Columbia','South','South Atlantic'),('WV','West Virginia','South','South Atlantic'),
 ('AL','Alabama','South','East South Central'),('KY','Kentucky','South','East South Central'),('MS','Mississippi','South','East South Central'),
 ('TN','Tennessee','South','East South Central'),
 ('AR','Arkansas','South','West South Central'),('LA','Louisiana','South','West South Central'),('OK','Oklahoma','South','West South Central'),
 ('TX','Texas','South','West South Central'),
 ('AZ','Arizona','West','Mountain'),('CO','Colorado','West','Mountain'),('ID','Idaho','West','Mountain'),('MT','Montana','West','Mountain'),
 ('NV','Nevada','West','Mountain'),('NM','New Mexico','West','Mountain'),('UT','Utah','West','Mountain'),('WY','Wyoming','West','Mountain'),
 ('AK','Alaska','West','Pacific'),('CA','California','West','Pacific'),('HI','Hawaii','West','Pacific'),('OR','Oregon','West','Pacific'),
 ('WA','Washington','West','Pacific'),
 ('PR','Puerto Rico','Territory','Territory'),('VI','Virgin Islands','Territory','Territory'),('GU','Guam','Territory','Territory'),
 ('AS','American Samoa','Territory','Territory'),('MP','Northern Mariana Islands','Territory','Territory'),('ZZ','Unknown/Foreign','Territory','Territory')
) AS t(state, state_name, census_region, census_division);
"""


def export(con: duckdb.DuckDBPyConnection) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    con.execute(STATE_REGION_SQL)

    tables = {
        # Dimensions
        "dim_year": """
            SELECT DISTINCT source_year AS year, CAST(source_year AS VARCHAR) AS year_label
            FROM gold_provider_year ORDER BY 1
        """,
        "dim_specialty": """
            SELECT DISTINCT provider_specialty AS specialty
            FROM gold_provider_year WHERE provider_specialty IS NOT NULL ORDER BY 1
        """,
        "dim_geography": """
            SELECT r.state, r.state_name, r.census_region, r.census_division
            FROM state_region r
            WHERE r.state IN (SELECT DISTINCT provider_state FROM gold_provider_year WHERE provider_state IS NOT NULL)
            ORDER BY 1
        """,
        "dim_provider": """
            SELECT
                rendering_npi,
                ANY_VALUE(provider_name ORDER BY source_year DESC)          AS provider_name,
                ANY_VALUE(provider_entity_type ORDER BY source_year DESC)   AS provider_entity_type,
                ANY_VALUE(provider_specialty ORDER BY source_year DESC)     AS provider_specialty,
                ANY_VALUE(provider_state ORDER BY source_year DESC)         AS provider_state,
                ANY_VALUE(provider_zip5 ORDER BY source_year DESC)          AS provider_zip5,
                ANY_VALUE(provider_ruca_code ORDER BY source_year DESC)     AS provider_ruca_code,
                ANY_VALUE(provider_ruca_desc ORDER BY source_year DESC)     AS provider_ruca_desc,
                ANY_VALUE(is_medicare_participating ORDER BY source_year DESC) AS is_medicare_participating_latest,
                MIN(source_year)                                            AS first_observed_year,
                MAX(source_year)                                            AS last_observed_year
            FROM gold_provider_year
            GROUP BY rendering_npi
        """,
        "dim_hcpcs": """
            SELECT
                hcpcs_code,
                ANY_VALUE(hcpcs_description ORDER BY source_year DESC) AS hcpcs_description,
                ANY_VALUE(is_drug_code ORDER BY source_year DESC)      AS is_drug_code
            FROM gold_procedure_year
            GROUP BY hcpcs_code
        """,
        "dim_place_of_service": """
            SELECT DISTINCT place_of_service FROM gold_provider_service_year WHERE place_of_service IS NOT NULL
        """,
        # Facts
        "fact_provider_year": """
            SELECT
                p.rendering_npi, p.source_year, p.provider_specialty, p.provider_state,
                p.distinct_hcpcs_codes, p.service_line_count,
                p.provider_total_beneficiaries, p.provider_total_services,
                p.provider_total_medicare_payment, p.provider_total_submitted_charge, p.provider_total_allowed_amount,
                p.payment_per_service, p.services_per_beneficiary, p.payment_per_beneficiary, p.payment_to_allowed_ratio,
                p.yoy_payment_change, p.yoy_payment_pct_change, p.yoy_services_change, p.yoy_services_pct_change,
                b.peer_group_size, b.benchmark_reliable,
                b.specialty_median_payment_per_beneficiary, b.specialty_p90_payment_per_beneficiary,
                b.percentile_rank_payment_per_beneficiary, b.relative_cost_ratio_beneficiary, b.robust_z_payment_per_beneficiary,
                COALESCE(o.is_high_cost_outlier, FALSE)         AS is_high_cost_outlier,
                COALESCE(o.methods_triggered_count, 0)          AS outlier_methods_triggered_count
            FROM gold_provider_year p
            LEFT JOIN gold_provider_benchmark b USING (rendering_npi, source_year)
            LEFT JOIN gold_provider_outlier o USING (rendering_npi, source_year)
        """,
        "fact_provider_service_year": "SELECT * FROM gold_provider_service_year",
        "fact_specialty_year": "SELECT * FROM gold_specialty_year",
        "fact_state_year": "SELECT * FROM gold_state_year",
        "fact_procedure_year": "SELECT * FROM gold_procedure_year",
        "fact_procedure_specialty_mix": "SELECT * FROM gold_procedure_specialty_mix",
    }

    # Model predictions are optional -- only present after src/modeling.py has run.
    has_predictions = con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'gold_model_predictions'"
    ).fetchone()[0]
    if has_predictions:
        tables["fact_model_predictions"] = "SELECT * FROM gold_model_predictions"

    for name, query in tables.items():
        out_path = OUT_DIR / f"{name}.parquet"
        con.execute(f"COPY ({query}) TO '{out_path.as_posix()}' (FORMAT PARQUET)")
        n = con.execute(f"SELECT COUNT(*) FROM ({query})").fetchone()[0]
        print(f"{name}: {n:,} rows -> {out_path.relative_to(REPO_ROOT)}")

    export_model_metrics()


def export_model_metrics() -> None:
    """Flatten reports/model_metrics.json (written by src/modeling.py) into a
    tidy metric-per-row table for Power BI cards. Skipped if modeling hasn't
    been run yet."""
    metrics_path = REPO_ROOT / "reports" / "model_metrics.json"
    if not metrics_path.exists():
        print("dim_model_metrics: skipped (reports/model_metrics.json not found -- run src/modeling.py first)")
        return

    raw = json.loads(metrics_path.read_text())
    rows = []
    m1 = raw["model1_payment_regression"]
    for metric in ("mae", "rmse", "r2"):
        rows.append({"model": "Model 1: Payment Prediction", "metric": metric.upper(), "value": m1[metric]})
    m2 = raw["model2_high_cost_classification"]
    for metric in ("precision", "recall", "f1", "roc_auc", "pr_auc"):
        rows.append({"model": "Model 2: High-Cost Classification", "metric": metric.replace("_", " ").upper(), "value": m2[metric]})

    df = pd.DataFrame(rows)
    out_path = OUT_DIR / "dim_model_metrics.parquet"
    df.to_parquet(out_path, index=False)
    print(f"dim_model_metrics: {len(df):,} rows -> {out_path.relative_to(REPO_ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Gold tables to Parquet for the Power BI semantic model.")
    parser.add_argument("--db", default=str(REPO_ROOT / "data" / "cms_medicare.duckdb"))
    args = parser.parse_args()
    con = duckdb.connect(args.db)
    export(con)
    con.close()


if __name__ == "__main__":
    sys.exit(main())
