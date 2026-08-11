"""
Feature construction for the two ML models, built on top of
gold_provider_year and gold_provider_benchmark (see sql/gold/).

Both models deliberately EXCLUDE features that are algebraically close to
their own target -- see reports/design_decisions.md, "Leakage risks", for
the full reasoning. This module is the single place that enforces that
exclusion so src/modeling.py can't accidentally reintroduce it.
"""

from __future__ import annotations

import duckdb
import pandas as pd

# Model 1 (payment prediction): practice-pattern and case-mix features only.
# Explicitly EXCLUDED: provider_total_services, payment_per_beneficiary,
# payment_per_service, provider_total_submitted_charge,
# provider_total_allowed_amount -- all are near-deterministic components or
# restatements of provider_total_medicare_payment (the target).
MODEL1_NUMERIC_FEATURES = [
    "distinct_hcpcs_codes",
    "service_line_count",
    "provider_ruca_code",
    "peer_group_size",
    "prior_year_payment",
    "prior_year_service_line_count",
    "is_medicare_participating",
]
MODEL1_CATEGORICAL_FEATURES = [
    "provider_specialty",
    "provider_state",
    "provider_entity_type",
]
MODEL1_TARGET = "provider_total_medicare_payment"

# Model 2 (high-cost classification): case-mix, geography, and utilization-
# INTENSITY features -- explicitly EXCLUDED: payment_per_beneficiary,
# payment_per_service, relative_cost_ratio, robust_z, percentile_rank --
# every one of those is the direct basis of the label itself (see
# design_decisions.md, "Model 2 circularity"). services_per_beneficiary is
# kept because it describes utilization volume, not payment amount.
MODEL2_NUMERIC_FEATURES = [
    "distinct_hcpcs_codes",
    "service_line_count",
    "provider_ruca_code",
    "services_per_beneficiary",
    "peer_group_size",
    "is_medicare_participating",
]
MODEL2_CATEGORICAL_FEATURES = [
    "provider_specialty",
    "provider_state",
    "provider_entity_type",
]
MODEL2_TARGET = "is_high_cost_p90"


def build_model1_frame(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Provider-year panel with a prior-year payment lag feature.
    Rows with no prior year (a provider's first observed year) get
    prior_year_payment = NULL, which XGBoost handles natively as missing."""
    df = con.execute("""
        SELECT
            rendering_npi, source_year, provider_specialty, provider_state,
            provider_entity_type, is_medicare_participating, provider_ruca_code,
            distinct_hcpcs_codes, service_line_count,
            provider_total_medicare_payment,
            LAG(provider_total_medicare_payment) OVER (PARTITION BY rendering_npi ORDER BY source_year)
                AS prior_year_payment,
            LAG(service_line_count) OVER (PARTITION BY rendering_npi ORDER BY source_year)
                AS prior_year_service_line_count
        FROM gold_provider_year
        WHERE provider_total_medicare_payment IS NOT NULL
          AND provider_total_medicare_payment > 0
    """).fetchdf()

    bench = con.execute("""
        SELECT rendering_npi, source_year, peer_group_size
        FROM gold_provider_benchmark
    """).fetchdf()
    df = df.merge(bench, on=["rendering_npi", "source_year"], how="left")
    return df


def build_model2_frame(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Benchmark-reliable provider-years only (peer_group_size >= 30 --
    see sql/gold/06_gold_provider_benchmark.sql), with the p90-percentile
    high-cost label and non-circular predictor features."""
    df = con.execute("""
        SELECT
            b.rendering_npi, b.source_year, b.provider_specialty, b.provider_state,
            p.provider_entity_type, p.is_medicare_participating, p.provider_ruca_code,
            p.distinct_hcpcs_codes, p.service_line_count, p.services_per_beneficiary,
            b.peer_group_size,
            (b.percentile_rank_payment_per_beneficiary >= 0.90)::INT AS is_high_cost_p90
        FROM gold_provider_benchmark b
        JOIN gold_provider_year p USING (rendering_npi, source_year)
        WHERE b.benchmark_reliable
    """).fetchdf()
    return df
