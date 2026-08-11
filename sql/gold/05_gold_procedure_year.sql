-- Gold: procedure_year
-- Grain: one row per (hcpcs_code, source_year), built from the full Silver
-- history (not the latest-year-only provider_service_year table), so
-- procedure-level spend and volume trends are available across all years
-- even though provider-level service-line detail is only kept for the
-- latest year.

CREATE OR REPLACE TABLE gold_procedure_year AS
WITH base AS (
    SELECT
        hcpcs_code,
        ANY_VALUE(hcpcs_description)                          AS hcpcs_description,
        ANY_VALUE(is_drug_code)                                AS is_drug_code,
        source_year,
        COUNT(DISTINCT rendering_npi)                          AS provider_count,
        SUM(total_services)                                    AS total_services,
        SUM(total_beneficiaries)                               AS total_beneficiary_lines,
        SUM(est_total_medicare_payment)                        AS total_medicare_payment,
        AVG(avg_medicare_payment_amt)                          AS avg_payment_per_service,
        MEDIAN(avg_medicare_payment_amt)                       AS median_payment_per_service
    FROM silver_physician_service
    GROUP BY hcpcs_code, source_year
)
SELECT
    *,
    total_medicare_payment
        - LAG(total_medicare_payment) OVER (PARTITION BY hcpcs_code ORDER BY source_year)
                                                                AS yoy_payment_change,
    total_medicare_payment
        / NULLIF(LAG(total_medicare_payment) OVER (PARTITION BY hcpcs_code ORDER BY source_year), 0) - 1
                                                                AS yoy_payment_pct_change
FROM base;

-- Procedure x specialty mix (for the "specialty mix" cut on Procedure
-- Intelligence): which specialties drive volume/spend for a given HCPCS
-- code, latest year only (keeps this table small; multi-year procedure
-- trend lives in gold_procedure_year above).
CREATE OR REPLACE TABLE gold_procedure_specialty_mix AS
SELECT
    s.hcpcs_code,
    s.provider_specialty,
    s.source_year,
    COUNT(DISTINCT s.rendering_npi)             AS provider_count,
    SUM(s.total_services)                        AS total_services,
    SUM(s.est_total_medicare_payment)            AS total_medicare_payment
FROM silver_physician_service s
WHERE s.source_year = (SELECT MAX(source_year) FROM silver_physician_service)
GROUP BY s.hcpcs_code, s.provider_specialty, s.source_year;
