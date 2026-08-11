-- Gold: provider_service_year
-- Grain: one row per (rendering_npi, hcpcs_code, place_of_service) for the
-- MOST RECENT loaded year only.
--
-- WHY LATEST YEAR ONLY: the full Silver grain across 6 years of national
-- CMS data is ~55-60M rows. That is comfortably within DuckDB's working set
-- for the Python/SQL layer, but it is not a reasonable size to import
-- wholesale into a Power BI Desktop *Import*-mode semantic model on typical
-- portfolio-reviewer hardware. Rather than silently truncate history or
-- ship a dashboard that chokes on load, this table deliberately trades
-- multi-year service-line detail for a full-detail *current* year, while
-- gold_provider_year / gold_specialty_year / gold_state_year /
-- gold_procedure_year keep full multi-year history at a pre-aggregated
-- grain that stays small regardless of years loaded. This is the fact
-- table behind Provider Intelligence's procedure-mix drill-through and all
-- of Procedure Intelligence.

CREATE OR REPLACE TABLE gold_provider_service_year AS
SELECT
    rendering_npi,
    source_year,
    hcpcs_code,
    hcpcs_description,
    is_drug_code,
    place_of_service,
    total_beneficiaries,
    total_services,
    total_bene_day_services,
    avg_submitted_charge,
    avg_medicare_allowed_amt,
    avg_medicare_payment_amt,
    avg_medicare_standardized_amt,
    est_total_medicare_payment,
    is_near_suppression_threshold
FROM silver_physician_service
WHERE source_year = (SELECT MAX(source_year) FROM silver_physician_service);
