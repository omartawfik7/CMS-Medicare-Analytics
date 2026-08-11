-- Gold: provider_outlier
-- Grain: one row per (rendering_npi, source_year) among providers with a
-- reliable specialty peer group (benchmark_reliable = TRUE in
-- gold_provider_benchmark, i.e. >= 30 providers in that specialty-year).
--
-- DISCLAIMER (repeat everywhere this table is surfaced -- README, DAX
-- measure descriptions, Power BI report text boxes):
-- "Statistical outliers represent unusual utilization or cost patterns
-- relative to peer providers and do not by themselves indicate fraud,
-- waste, abuse, or improper billing."
--
-- Three independent, standard methods are computed on payment_per_beneficiary
-- (the primary cost-per-patient metric); a provider is flagged
-- high-cost-review if ANY method trips, and the specific method(s) are
-- kept so a reviewer can see whether the signal is robust across methods
-- or an artifact of one:
--   1. Percentile method: at/above the 90th percentile within specialty-year.
--   2. IQR (Tukey) method: above specialty_p75 + 1.5 * specialty_IQR.
--   3. Robust z-score (MAD) method: robust z > 3.5 (Iglewicz & Hoaglin,
--      1993 -- the commonly used threshold for MAD-based outlier flags).

CREATE OR REPLACE TABLE gold_provider_outlier AS
WITH flagged AS (
    SELECT
        b.rendering_npi,
        b.source_year,
        b.provider_specialty,
        b.provider_state,
        b.peer_group_size,
        b.payment_per_beneficiary,
        b.percentile_rank_payment_per_beneficiary,
        b.relative_cost_ratio_beneficiary,
        b.robust_z_payment_per_beneficiary,
        b.specialty_median_payment_per_beneficiary,
        b.specialty_p75_payment_per_beneficiary,
        b.specialty_p90_payment_per_beneficiary,
        b.specialty_iqr_payment_per_beneficiary,

        b.percentile_rank_payment_per_beneficiary >= 0.90
                                                              AS flag_percentile_method,
        b.payment_per_beneficiary > (
            b.specialty_p75_payment_per_beneficiary + 1.5 * b.specialty_iqr_payment_per_beneficiary
        )                                                     AS flag_iqr_method,
        b.robust_z_payment_per_beneficiary > 3.5               AS flag_robust_z_method
    FROM gold_provider_benchmark b
    WHERE b.benchmark_reliable
)
SELECT
    rendering_npi,
    source_year,
    provider_specialty,
    provider_state,
    peer_group_size,
    payment_per_beneficiary,
    specialty_median_payment_per_beneficiary,
    percentile_rank_payment_per_beneficiary,
    relative_cost_ratio_beneficiary,
    robust_z_payment_per_beneficiary,
    flag_percentile_method,
    flag_iqr_method,
    flag_robust_z_method,
    (flag_percentile_method::INT + flag_iqr_method::INT + flag_robust_z_method::INT)
                                                              AS methods_triggered_count,
    (flag_percentile_method OR flag_iqr_method OR flag_robust_z_method)
                                                              AS is_high_cost_outlier,
    'Statistical outliers represent unusual utilization or cost patterns relative to peer providers and do not by themselves indicate fraud, waste, abuse, or improper billing.'
                                                              AS methodology_disclaimer
FROM flagged
WHERE flag_percentile_method OR flag_iqr_method OR flag_robust_z_method;
