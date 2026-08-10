# Data sources

## Dataset

**Medicare Physician & Other Practitioners - by Provider and Service**
Published by CMS (Centers for Medicare & Medicaid Services), Office of Enterprise Data and Analytics.

- Grain: one row per (rendering NPI, HCPCS/service code, place of service), per calendar year.
- Homepage: https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners/medicare-physician-other-practitioners-by-provider-and-service
- Methodology PDF: https://data.cms.gov/sites/default/files/2023-05/b4775e86-72aa-40de-b048-9d9fdad1cd09/MUP_PHY_RY23_20230509_Methology_508.pdf
- Update frequency: annual, ~12-15 month lag (CY2023 data was released in 2025).
- License: public domain (U.S. government work); HCPCS descriptions include AMA CPT content included as provided by CMS.

This is 100% *aggregate* CMS claims data. It is **not** individual patient
records, EHR data, or PHI -- there is no beneficiary-level information in
this file, only provider x service x year summary statistics.

## Confirmed download locations (verified live 2026-08-10)

See `config/cms_sources.yaml` for the machine-readable version. Direct CSV
downloads, most recent five years:

| Year | CSV URL |
|---|---|
| 2023 | https://data.cms.gov/sites/default/files/2025-04/e3f823f8-db5b-4cc7-ba04-e7ae92b99757/MUP_PHY_R25_P05_V20_D23_Prov_Svc.csv |
| 2022 | https://data.cms.gov/sites/default/files/2025-11/53fb2bae-4913-48dc-a6d4-d8c025906567/MUP_PHY_R25_P05_V20_D22_Prov_Svc.csv |
| 2021 | https://data.cms.gov/sites/default/files/2025-11/bffaf97a-c2ab-4fd7-8718-be90742e3485/MUP_PHY_R25_P05_V20_D21_Prov_Svc.csv |
| 2020 | https://data.cms.gov/sites/default/files/2025-11/d22b18cd-7726-4bf5-8e9c-3e4587c589a1/MUP_PHY_R25_P05_V20_D20_Prov_Svc.csv |
| 2019 | https://data.cms.gov/sites/default/files/2025-11/7befba27-752e-47a8-a76c-6c6d4f74f2e3/MUP_PHY_R25_P04_V20_D19_Prov_Svc.csv |

Full history back to 2013 is available; see `config/cms_sources.yaml`.

## How to download the full file(s)

This environment's sandbox cannot reach `data.cms.gov` directly (network
egress is restricted to package registries and GitHub), so full-scale
downloads need to happen on your own machine or CI runner:

```bash
mkdir -p data/raw
curl -L -o data/raw/MUP_PHY_2023_Prov_Svc.csv \
  "https://data.cms.gov/sites/default/files/2025-04/e3f823f8-db5b-4cc7-ba04-e7ae92b99757/MUP_PHY_R25_P05_V20_D23_Prov_Svc.csv"
```

Then run ingestion exactly as with the sample:

```bash
python src/ingestion.py --csv data/raw/MUP_PHY_2023_Prov_Svc.csv --year 2023 --vintage R25_P05_V20_D23
```

The same `src/ingestion.py` code path handles both the small sample and the
full ~9-10M row annual file -- only the input path changes.

## Measured scale (from CMS's own published dataset stats)

- **CY2023 file**: ~9-10M rows (provider x HCPCS x place-of-service grain),
  consistent with every other year 2013-2023 in this series.
- **Across CY2013-CY2024 (12 years)**: 116,190,383 rows total in the
  provider-and-service grain alone, per an independently-built full-history
  DuckDB extract of this same CMS series (~9.7M rows/year average).
- Uncompressed CSV size per year is in the **2-3 GB range** (29 columns,
  mostly text + a handful of numeric fields, ~9-10M rows).

This comfortably fits DuckDB running locally (DuckDB is commonly used for
tables well into the 100M-1B row range on a laptop) -- there is no reason to
reach for Databricks or a distributed engine for the single-year MVP, or
even for the full 2013-2024 multi-year history unless the project later adds
much larger joined datasets (e.g. full NPPES registry, full Census ACS
block-group tables).

## Sample file for schema validation

`data/raw/sample_mup_phy_provider_service_2023.csv` contains 37 rows of
**real, unmodified 2023 CMS data** (pulled from the live
`data.cms.gov/data-api/v1/dataset/92396110-2aed-4d63-a6a2-5d6207d46a29/data`
endpoint), spanning 12 distinct providers, 31 distinct HCPCS codes, and 7
provider specialties. It exists purely so the Bronze/Silver/Gold pipeline
in this repo can be run and reviewed without a multi-GB download, and so
that every field name, data type, and value pattern documented in this repo
is provably real rather than assumed. It is committed to git (unlike the
full-size files, which are gitignored).

## Known limitations (see also reports/data_limitations.md)

1. **Suppression**: CMS omits any (provider, HCPCS, place-of-service) line
   with fewer than 11 unique beneficiaries, to protect patient privacy. This
   is not random -- it systematically removes low-volume, often
   lower-cost, service lines, which means provider-level sums from this
   file *undercount* true totals (by an estimated 17-21% in independent
   audits comparing this file to CMS's own provider-level summary file).
2. **Fee-for-service only**: this file only covers Original Medicare (Part
   B fee-for-service) claims. Medicare Advantage enrollees are entirely
   absent, which is a large and non-random share of the Medicare
   population and skews geographically.
3. **No beneficiary demographics or clinical detail** in this file (that
   lives in the separate "by Provider" summary file, at the provider grain
   only, not service-line grain).
4. **Averages, not totals, for payment fields**: `Avg_Mdcr_Pymt_Amt` etc.
   are per-service averages; `est_total_medicare_payment` in Silver is a
   derived multiply-through and inherits any rounding in the source
   averages.
