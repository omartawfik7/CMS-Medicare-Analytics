-- Gold: state_year
-- Grain: one row per (provider_state, source_year).
-- Purpose: Geographic Intelligence page -- state-level spend, providers,
-- utilization, and share-of-national-spend, over time.
-- NOTE: state = rendering provider's practice location (not beneficiary
-- residence -- this file has no beneficiary geography).

CREATE OR REPLACE TABLE gold_state_year AS
WITH base AS (
    SELECT
        provider_state,
        source_year,
        COUNT(DISTINCT rendering_npi)                        AS provider_count,
        SUM(provider_total_beneficiaries)                    AS state_total_beneficiary_lines,
        SUM(provider_total_services)                          AS state_total_services,
        SUM(provider_total_medicare_payment)                  AS state_total_medicare_payment,
        SUM(provider_total_medicare_payment) / NULLIF(COUNT(DISTINCT rendering_npi), 0)
                                                                AS payment_per_provider,
        SUM(provider_total_medicare_payment) / NULLIF(SUM(provider_total_beneficiaries), 0)
                                                                AS payment_per_beneficiary
    FROM gold_provider_year
    WHERE provider_state IS NOT NULL AND provider_state != ''
    GROUP BY provider_state, source_year
),
with_share AS (
    SELECT
        *,
        state_total_medicare_payment / NULLIF(SUM(state_total_medicare_payment) OVER (PARTITION BY source_year), 0)
                                                                AS state_share_of_national_spend
    FROM base
)
SELECT
    *,
    state_total_medicare_payment
        - LAG(state_total_medicare_payment) OVER (PARTITION BY provider_state ORDER BY source_year)
                                                                AS yoy_payment_change,
    state_total_medicare_payment
        / NULLIF(LAG(state_total_medicare_payment) OVER (PARTITION BY provider_state ORDER BY source_year), 0) - 1
                                                                AS yoy_payment_pct_change
FROM with_share;
