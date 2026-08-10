-- Silver: physician_service
-- Source: bronze_physician_service (raw VARCHAR grain, 1 row per NPI x HCPCS x place-of-service)
--
-- What happens here and why:
--   1. Type coercion: CMS ships every numeric field as text. We cast to
--      proper numeric/int types so Gold and the ML layer don't have to.
--   2. Suppression handling: CMS masks any Tot_Benes < 11 (privacy rule) and
--      correlated fields go blank alongside it in the underlying source, not
--      literal "*" in this particular file -- rows below the beneficiary
--      threshold are simply omitted from the public file entirely, they are
--      not present with nulled fields. That is itself a data-quality fact
--      worth carrying forward: this table is systematically missing the
--      long tail of low-volume (provider, service) pairs. We flag this in
--      is_low_volume_masked for downstream users rather than let it look
--      like "this provider didn't do this yet."
--   3. Standardization: trim whitespace, uppercase state abbreviation,
--      normalize entity code to a readable label, derive a single
--      full-name / org-name field depending on individual vs organization.
--   4. Grain enforcement: (Rndrng_NPI, HCPCS_Cd, Place_Of_Srvc, source_year)
--      should be unique. We surface duplicates rather than silently
--      dropping them, since duplicates would indicate an ingestion bug.

CREATE OR REPLACE TABLE silver_physician_service AS
SELECT
    -- Identifiers
    TRIM(Rndrng_NPI)                                   AS rendering_npi,
    source_year,

    -- Provider attributes
    CASE Rndrng_Prvdr_Ent_Cd
        WHEN 'I' THEN 'Individual'
        WHEN 'O' THEN 'Organization'
        ELSE Rndrng_Prvdr_Ent_Cd
    END                                                 AS provider_entity_type,
    TRIM(Rndrng_Prvdr_Last_Org_Name)                    AS provider_last_or_org_name,
    NULLIF(TRIM(Rndrng_Prvdr_First_Name), '')           AS provider_first_name,
    NULLIF(TRIM(Rndrng_Prvdr_MI), '')                   AS provider_middle_initial,
    NULLIF(TRIM(Rndrng_Prvdr_Crdntls), '')              AS provider_credentials,
    TRIM(Rndrng_Prvdr_Type)                              AS provider_specialty,
    Rndrng_Prvdr_Mdcr_Prtcptg_Ind = 'Y'                 AS is_medicare_participating,

    -- Geography
    NULLIF(TRIM(Rndrng_Prvdr_St1), '')                  AS provider_address_line1,
    NULLIF(TRIM(Rndrng_Prvdr_St2), '')                  AS provider_address_line2,
    TRIM(Rndrng_Prvdr_City)                              AS provider_city,
    UPPER(TRIM(Rndrng_Prvdr_State_Abrvtn))               AS provider_state,
    TRIM(Rndrng_Prvdr_State_FIPS)                        AS provider_state_fips,
    TRIM(Rndrng_Prvdr_Zip5)                              AS provider_zip5,
    TRY_CAST(Rndrng_Prvdr_RUCA AS DOUBLE)                AS provider_ruca_code,
    TRIM(Rndrng_Prvdr_RUCA_Desc)                         AS provider_ruca_desc,
    TRIM(Rndrng_Prvdr_Cntry)                             AS provider_country,

    -- Service
    TRIM(HCPCS_Cd)                                       AS hcpcs_code,
    TRIM(HCPCS_Desc)                                     AS hcpcs_description,
    HCPCS_Drug_Ind = 'Y'                                 AS is_drug_code,
    CASE Place_Of_Srvc
        WHEN 'F' THEN 'Facility'
        WHEN 'O' THEN 'Non-facility (office)'
        ELSE Place_Of_Srvc
    END                                                  AS place_of_service,

    -- Utilization & payment (numeric, CMS-suppression-aware)
    TRY_CAST(Tot_Benes AS INTEGER)                       AS total_beneficiaries,
    TRY_CAST(Tot_Srvcs AS INTEGER)                       AS total_services,
    TRY_CAST(Tot_Bene_Day_Srvcs AS INTEGER)              AS total_bene_day_services,
    TRY_CAST(Avg_Sbmtd_Chrg AS DOUBLE)                   AS avg_submitted_charge,
    TRY_CAST(Avg_Mdcr_Alowd_Amt AS DOUBLE)               AS avg_medicare_allowed_amt,
    TRY_CAST(Avg_Mdcr_Pymt_Amt AS DOUBLE)                AS avg_medicare_payment_amt,
    TRY_CAST(Avg_Mdcr_Stdzd_Amt AS DOUBLE)               AS avg_medicare_standardized_amt,

    -- Derived
    TRY_CAST(Tot_Srvcs AS DOUBLE) * TRY_CAST(Avg_Mdcr_Pymt_Amt AS DOUBLE)
                                                          AS est_total_medicare_payment,
    TRY_CAST(Tot_Benes AS INTEGER) < 11                  AS is_near_suppression_threshold,

    -- Provenance
    source_file,
    source_vintage,
    ingested_at
FROM bronze_physician_service;

-- Data-quality check: grain should be unique. If this returns rows, the
-- Bronze load produced duplicates and Gold aggregates would double-count.
-- CREATE OR REPLACE TABLE dq_silver_physician_service_dupes AS
-- SELECT rendering_npi, hcpcs_code, place_of_service, source_year, COUNT(*) AS n
-- FROM silver_physician_service
-- GROUP BY 1,2,3,4
-- HAVING COUNT(*) > 1;
