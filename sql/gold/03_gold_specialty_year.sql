-- Gold: specialty_year
-- Grain: one row per (provider_specialty, source_year).
-- Purpose: Specialty Intelligence page -- spend, provider count,
-- utilization, and share-of-national-spend by specialty, over time.

CREATE OR REPLACE TABLE gold_specialty_year AS
WITH base AS (
    SELECT
        provider_specialty,
        source_year,
        COUNT(DISTINCT rendering_npi)                       AS provider_count,
        SUM(provider_total_beneficiaries)                   AS specialty_total_beneficiary_lines,
        SUM(provider_total_services)                         AS specialty_total_services,
        SUM(provider_total_medicare_payment)                 AS specialty_total_medicare_payment,
        AVG(payment_per_beneficiary)                          AS specialty_avg_payment_per_beneficiary,
        MEDIAN(payment_per_beneficiary)                       AS specialty_median_payment_per_beneficiary,
        MEDIAN(payment_per_service)                           AS specialty_median_payment_per_service,
        SUM(provider_total_medicare_payment) / NULLIF(COUNT(DISTINCT rendering_npi), 0)
                                                               AS payment_per_provider,
        SUM(provider_total_services) / NULLIF(COUNT(DISTINCT rendering_npi), 0)
                                                               AS services_per_provider
    FROM gold_provider_year
    WHERE provider_specialty IS NOT NULL
    GROUP BY provider_specialty, source_year
),
with_share AS (
    SELECT
        *,
        specialty_total_medicare_payment / NULLIF(SUM(specialty_total_medicare_payment) OVER (PARTITION BY source_year), 0)
                                                               AS specialty_share_of_national_spend
    FROM base
)
SELECT
    *,
    specialty_total_medicare_payment
        - LAG(specialty_total_medicare_payment) OVER (PARTITION BY provider_specialty ORDER BY source_year)
                                                               AS yoy_payment_change,
    specialty_total_medicare_payment
        / NULLIF(LAG(specialty_total_medicare_payment) OVER (PARTITION BY provider_specialty ORDER BY source_year), 0) - 1
                                                               AS yoy_payment_pct_change
FROM with_share;
