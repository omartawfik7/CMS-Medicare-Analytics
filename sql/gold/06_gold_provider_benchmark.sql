-- Gold: provider_benchmark
-- Grain: one row per (rendering_npi, source_year).
-- Purpose: specialty-adjusted peer benchmarking. A provider is only ever
-- compared to other providers in the SAME specialty and SAME year -- never
-- across specialties, since a cardiac surgeon and a family physician have
-- entirely different cost/utilization profiles by the nature of their work.
--
-- MINIMUM PEER GROUP SIZE: percentiles, medians, and MAD computed over a
-- handful of providers are unstable and can make one provider's specialty
-- look arbitrarily extreme. We require >= 30 providers in a
-- (specialty, year) cell before treating it as a valid peer group. Rather
-- than invent a broader specialty taxonomy that doesn't exist in the CMS
-- source file (Rndrng_Prvdr_Type is a flat, ungrouped list of ~100+
-- specialty labels), specialty-year cells below the threshold are marked
-- benchmark_reliable = FALSE and their percentile/z-score/ratio columns are
-- left NULL rather than computed on an unstable base. This is a deliberate,
-- documented trade-off (see reports/design_decisions.md item 5).
--
-- METHODS COMPUTED (all specialty x year, on payment_per_beneficiary and
-- payment_per_service):
--   - specialty_median / specialty_p25 / specialty_p75 / specialty_p90
--   - IQR = p75 - p25
--   - MAD = median(|x - median(x)|), scaled by 0.6745 for a normal-
--     consistent robust z-score (Iglewicz & Hoaglin, 1993)
--   - percentile_rank (0-1, PERCENT_RANK within the peer group)
--   - relative_cost_ratio = provider value / specialty median

CREATE OR REPLACE TABLE gold_provider_benchmark AS
WITH peer_stats AS (
    SELECT
        provider_specialty,
        source_year,
        COUNT(*)                                                    AS peer_group_size,
        MEDIAN(payment_per_beneficiary)                              AS specialty_median_ppb,
        QUANTILE_CONT(payment_per_beneficiary, 0.25)                 AS specialty_p25_ppb,
        QUANTILE_CONT(payment_per_beneficiary, 0.75)                 AS specialty_p75_ppb,
        QUANTILE_CONT(payment_per_beneficiary, 0.90)                 AS specialty_p90_ppb,
        MAD(payment_per_beneficiary)                                 AS specialty_mad_ppb,
        MEDIAN(payment_per_service)                                  AS specialty_median_pps,
        QUANTILE_CONT(payment_per_service, 0.25)                     AS specialty_p25_pps,
        QUANTILE_CONT(payment_per_service, 0.75)                     AS specialty_p75_pps,
        QUANTILE_CONT(payment_per_service, 0.90)                     AS specialty_p90_pps,
        MAD(payment_per_service)                                     AS specialty_mad_pps
    FROM gold_provider_year
    WHERE provider_specialty IS NOT NULL
      AND payment_per_beneficiary IS NOT NULL
      AND payment_per_beneficiary > 0
    GROUP BY provider_specialty, source_year
),
ranked AS (
    SELECT
        p.rendering_npi,
        p.source_year,
        p.provider_specialty,
        p.provider_state,
        p.payment_per_beneficiary,
        p.payment_per_service,
        s.peer_group_size,
        s.peer_group_size >= 30                                      AS benchmark_reliable,
        s.specialty_median_ppb, s.specialty_p25_ppb, s.specialty_p75_ppb, s.specialty_p90_ppb, s.specialty_mad_ppb,
        s.specialty_median_pps, s.specialty_p25_pps, s.specialty_p75_pps, s.specialty_p90_pps, s.specialty_mad_pps,
        PERCENT_RANK() OVER (
            PARTITION BY p.provider_specialty, p.source_year ORDER BY p.payment_per_beneficiary
        )                                                             AS percentile_rank_ppb,
        PERCENT_RANK() OVER (
            PARTITION BY p.provider_specialty, p.source_year ORDER BY p.payment_per_service
        )                                                             AS percentile_rank_pps
    FROM gold_provider_year p
    JOIN peer_stats s USING (provider_specialty, source_year)
    WHERE p.payment_per_beneficiary IS NOT NULL AND p.payment_per_beneficiary > 0
)
SELECT
    rendering_npi,
    source_year,
    provider_specialty,
    provider_state,
    payment_per_beneficiary,
    payment_per_service,
    peer_group_size,
    benchmark_reliable,

    CASE WHEN benchmark_reliable THEN specialty_median_ppb END        AS specialty_median_payment_per_beneficiary,
    CASE WHEN benchmark_reliable THEN specialty_p25_ppb END           AS specialty_p25_payment_per_beneficiary,
    CASE WHEN benchmark_reliable THEN specialty_p75_ppb END           AS specialty_p75_payment_per_beneficiary,
    CASE WHEN benchmark_reliable THEN specialty_p75_ppb - specialty_p25_ppb END
                                                                       AS specialty_iqr_payment_per_beneficiary,
    CASE WHEN benchmark_reliable THEN specialty_p90_ppb END           AS specialty_p90_payment_per_beneficiary,
    CASE WHEN benchmark_reliable THEN percentile_rank_ppb END         AS percentile_rank_payment_per_beneficiary,
    CASE WHEN benchmark_reliable AND specialty_median_ppb > 0
         THEN payment_per_beneficiary / specialty_median_ppb END      AS relative_cost_ratio_beneficiary,
    CASE WHEN benchmark_reliable AND specialty_mad_ppb > 0
         THEN 0.6745 * (payment_per_beneficiary - specialty_median_ppb) / specialty_mad_ppb END
                                                                       AS robust_z_payment_per_beneficiary,

    CASE WHEN benchmark_reliable THEN specialty_median_pps END        AS specialty_median_payment_per_service,
    CASE WHEN benchmark_reliable THEN specialty_p75_pps - specialty_p25_pps END
                                                                       AS specialty_iqr_payment_per_service,
    CASE WHEN benchmark_reliable THEN specialty_p90_pps END           AS specialty_p90_payment_per_service,
    CASE WHEN benchmark_reliable THEN percentile_rank_pps END         AS percentile_rank_payment_per_service,
    CASE WHEN benchmark_reliable AND specialty_median_pps > 0
         THEN payment_per_service / specialty_median_pps END          AS relative_cost_ratio_service,
    CASE WHEN benchmark_reliable AND specialty_mad_pps > 0
         THEN 0.6745 * (payment_per_service - specialty_median_pps) / specialty_mad_pps END
                                                                       AS robust_z_payment_per_service
FROM ranked;
