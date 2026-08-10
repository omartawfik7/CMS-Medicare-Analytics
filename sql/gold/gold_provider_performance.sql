-- Gold: provider_performance
-- Grain: one row per (rendering_npi, source_year)
-- Purpose: the base analytical table for provider benchmarking, outlier
-- detection, and Model 1 (payment prediction). Aggregates the Silver
-- service-line grain up to the provider level.
--
-- NOTE ON SUPPRESSION: because low-volume (provider, HCPCS) lines are
-- omitted from the source file below CMS's beneficiary-count threshold,
-- provider_total_services and provider_total_payment here are undercounts
-- for providers with many low-volume service lines. This is a systematic
-- bias, not random noise -- see reports/data_limitations.md.

CREATE OR REPLACE TABLE gold_provider_performance AS
SELECT
    rendering_npi,
    source_year,
    ANY_VALUE(provider_last_or_org_name)      AS provider_name,
    ANY_VALUE(provider_entity_type)           AS provider_entity_type,
    ANY_VALUE(provider_specialty)             AS provider_specialty,
    ANY_VALUE(provider_state)                 AS provider_state,
    ANY_VALUE(provider_zip5)                  AS provider_zip5,
    ANY_VALUE(provider_ruca_code)             AS provider_ruca_code,
    ANY_VALUE(is_medicare_participating)      AS is_medicare_participating,

    COUNT(DISTINCT hcpcs_code)                AS distinct_hcpcs_codes,
    COUNT(*)                                  AS service_line_count,
    SUM(total_beneficiaries)                  AS provider_total_beneficiaries,
    SUM(total_services)                       AS provider_total_services,
    SUM(est_total_medicare_payment)           AS provider_total_medicare_payment,
    AVG(avg_medicare_payment_amt)             AS provider_avg_payment_per_service_line,
    SUM(total_services) / NULLIF(SUM(total_beneficiaries), 0)
                                               AS services_per_beneficiary,
    SUM(est_total_medicare_payment) / NULLIF(SUM(total_beneficiaries), 0)
                                               AS payment_per_beneficiary,

    SUM(CASE WHEN is_near_suppression_threshold THEN 1 ELSE 0 END)
                                               AS n_near_suppression_lines
FROM silver_physician_service
GROUP BY rendering_npi, source_year;

-- Specialty-adjusted benchmark: how a provider's payment-per-beneficiary
-- compares to the median for their own specialty in the same year. This is
-- the core of the "specialty-adjusted benchmark" analysis, not a raw
-- cross-specialty comparison (which would be meaningless -- a cardiac
-- surgeon and a family physician have entirely different cost profiles).
CREATE OR REPLACE TABLE gold_specialty_benchmarks AS
SELECT
    p.*,
    b.specialty_median_payment_per_bene,
    b.specialty_p75_payment_per_bene,
    b.specialty_p90_payment_per_bene,
    p.payment_per_beneficiary / NULLIF(b.specialty_median_payment_per_bene, 0)
                                               AS payment_ratio_to_specialty_median
FROM gold_provider_performance p
JOIN (
    SELECT
        provider_specialty,
        source_year,
        MEDIAN(payment_per_beneficiary)                         AS specialty_median_payment_per_bene,
        QUANTILE_CONT(payment_per_beneficiary, 0.75)             AS specialty_p75_payment_per_bene,
        QUANTILE_CONT(payment_per_beneficiary, 0.90)             AS specialty_p90_payment_per_bene
    FROM gold_provider_performance
    GROUP BY provider_specialty, source_year
) b USING (provider_specialty, source_year);
