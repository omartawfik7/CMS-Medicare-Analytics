-- Gold: provider_year
-- Grain: one row per (rendering_npi, source_year)
-- Purpose: the base analytical table for provider benchmarking, outlier
-- detection, and Model 1 (payment prediction). Aggregates the Silver
-- service-line grain up to the provider level, across all loaded years.
--
-- NOTE ON SUPPRESSION: because low-volume (provider, HCPCS) lines are
-- omitted from the source file below CMS's beneficiary-count threshold,
-- provider_total_services and provider_total_medicare_payment here are
-- undercounts for providers with many low-volume service lines. This is a
-- systematic bias, not random noise -- see data/README.md.
--
-- NOTE ON BENEFICIARY COUNTS: provider_total_beneficiaries is a SUM of
-- per-service-line unique-beneficiary counts. A beneficiary who received
-- three different services from the same provider is counted three times
-- here (once per service line), because the source file does not expose
-- provider-level unique beneficiary counts. This is a real overcount, not
-- a bug -- treat it as "beneficiary-service-line incidents", not "unique
-- patients", and do not compare it directly to CMS's separate by-Provider
-- summary file, which does report true unique beneficiaries per provider.

CREATE OR REPLACE TABLE gold_provider_year AS
WITH base AS (
    SELECT
        rendering_npi,
        source_year,
        ANY_VALUE(provider_last_or_org_name)      AS provider_name,
        ANY_VALUE(provider_entity_type)           AS provider_entity_type,
        ANY_VALUE(provider_specialty)             AS provider_specialty,
        ANY_VALUE(provider_state)                 AS provider_state,
        ANY_VALUE(provider_zip5)                  AS provider_zip5,
        ANY_VALUE(provider_ruca_code)              AS provider_ruca_code,
        ANY_VALUE(provider_ruca_desc)              AS provider_ruca_desc,
        ANY_VALUE(is_medicare_participating)      AS is_medicare_participating,

        COUNT(DISTINCT hcpcs_code)                AS distinct_hcpcs_codes,
        COUNT(*)                                  AS service_line_count,
        SUM(total_beneficiaries)                  AS provider_total_beneficiaries,
        SUM(total_services)                       AS provider_total_services,
        SUM(est_total_medicare_payment)           AS provider_total_medicare_payment,
        SUM(total_services * avg_submitted_charge)     AS provider_total_submitted_charge,
        SUM(total_services * avg_medicare_allowed_amt) AS provider_total_allowed_amount,
        AVG(avg_medicare_payment_amt)             AS provider_avg_payment_per_service_line,

        SUM(est_total_medicare_payment) / NULLIF(SUM(total_services), 0)
                                                   AS payment_per_service,
        SUM(total_services) / NULLIF(SUM(total_beneficiaries), 0)
                                                   AS services_per_beneficiary,
        SUM(est_total_medicare_payment) / NULLIF(SUM(total_beneficiaries), 0)
                                                   AS payment_per_beneficiary,
        SUM(est_total_medicare_payment) / NULLIF(SUM(total_services * avg_medicare_allowed_amt), 0)
                                                   AS payment_to_allowed_ratio,

        SUM(CASE WHEN is_near_suppression_threshold THEN 1 ELSE 0 END)
                                                   AS n_near_suppression_lines
    FROM silver_physician_service
    GROUP BY rendering_npi, source_year
)
SELECT
    *,
    provider_total_medicare_payment
        - LAG(provider_total_medicare_payment) OVER (PARTITION BY rendering_npi ORDER BY source_year)
                                                   AS yoy_payment_change,
    provider_total_medicare_payment
        / NULLIF(LAG(provider_total_medicare_payment) OVER (PARTITION BY rendering_npi ORDER BY source_year), 0) - 1
                                                   AS yoy_payment_pct_change,
    provider_total_services
        - LAG(provider_total_services) OVER (PARTITION BY rendering_npi ORDER BY source_year)
                                                   AS yoy_services_change,
    provider_total_services
        / NULLIF(LAG(provider_total_services) OVER (PARTITION BY rendering_npi ORDER BY source_year), 0) - 1
                                                   AS yoy_services_pct_change
FROM base;
