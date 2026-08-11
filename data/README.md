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

## Confirmed download locations (verified live 2026-08-11)

See `config/cms_sources.yaml` for the machine-readable version.

| Year | CSV URL |
|---|---|
| 2023 | https://data.cms.gov/sites/default/files/2025-04/e3f823f8-db5b-4cc7-ba04-e7ae92b99757/MUP_PHY_R25_P05_V20_D23_Prov_Svc.csv |
| 2022 | https://data.cms.gov/sites/default/files/2025-11/53fb2bae-4913-48dc-a6d4-d8c025906567/MUP_PHY_R25_P05_V20_D22_Prov_Svc.csv |
| 2021 | https://data.cms.gov/sites/default/files/2025-11/bffaf97a-c2ab-4fd7-8718-be90742e3485/MUP_PHY_R25_P05_V20_D21_Prov_Svc.csv |
| 2020 | https://data.cms.gov/sites/default/files/2025-11/d22b18cd-7726-4bf5-8e9c-3e4587c589a1/MUP_PHY_R25_P05_V20_D20_Prov_Svc.csv |
| 2019 | https://data.cms.gov/sites/default/files/2025-11/7befba27-752e-47a8-a76c-6c6d4f74f2e3/MUP_PHY_R25_P04_V20_D19_Prov_Svc.csv |
| 2018 | https://data.cms.gov/sites/default/files/2025-11/5669eafb-f0b3-4dc5-be6d-abc09b480c2e/MUP_PHY_R25_P04_V20_D18_Prov_Svc.csv |

Full history back to 2013 is available at the same pattern; see
`config/cms_sources.yaml` to extend the `years:` map.

## How to download the full file(s)

`data.cms.gov` bulk CSV downloads are directly reachable from wherever you
run this pipeline (verified: sustained 22-67 MB/s in the sandbox this
project was built in). Use `src/ingest_cms.py`, not manual `curl` -- it adds
retries with exponential backoff, resumable downloads via HTTP Range,
SHA-256 checksums, row-count verification, and a `data/raw/manifest.json`
provenance record (source URL, download timestamp, file size, row count,
checksum) per year:

```bash
python src/ingest_cms.py --years 2018 2019 2020 2021 2022 2023
```

This downloads each year's ~3GB CSV to `data/raw/` (gitignored) and loads it
straight into DuckDB Bronze via `src/ingestion.py`'s `load_bronze()`. Add
`--skip-bronze` to only download, or `--force-download` to re-pull a year
already present locally. Re-running for an already-downloaded, unchanged
year is a fast no-op.

If your environment genuinely cannot reach `data.cms.gov` (some sandboxes
restrict egress to package registries + GitHub only), download manually on
a machine that can and point `--csv` at the local file with
`src/ingestion.py` directly -- see that script's docstring.

## Measured scale (actual, from this run -- not estimated)

| Year | Rows | File size |
|---|---:|---:|
| 2018 | 9,961,865 | 3.13 GB |
| 2019 | 10,140,228 | 3.18 GB |
| 2020 | 9,449,361 | 2.99 GB |
| 2021 | 9,886,177 | 3.10 GB |
| 2022 | 9,755,427 | 3.07 GB |
| 2023 | 9,660,647 | 3.06 GB |
| **Total** | **58,853,705** | **~18.4 GB** |

This comfortably fits DuckDB running locally (the full Bronze load + Silver
+ all 7 Gold scripts, including specialty-adjusted benchmarking and outlier
detection over 6.7M provider-years, complete in well under 3 minutes
combined on a 20-core/31GB machine) -- there is no reason to reach for
Databricks or a distributed engine at this scale, and likely not even for
the full 2013-2024 history (~116M rows) unless the project later adds much
larger joined datasets (e.g. full NPPES registry, full Census ACS
block-group tables).

## Sample file for schema validation

`data/raw/sample_mup_phy_provider_service_2023.csv` contains 37 rows of
**real, unmodified 2023 CMS data** (pulled from the live
`data.cms.gov/data-api/v1/dataset/92396110-2aed-4d63-a6a2-5d6207d46a29/data`
endpoint), spanning 12 distinct providers, 31 distinct HCPCS codes, and 11
provider specialties. It exists purely so the Bronze/Silver/Gold pipeline
in this repo can be run and reviewed without a multi-GB download, and so
that every field name, data type, and value pattern documented in this repo
is provably real rather than assumed. It is committed to git (unlike the
full-size files, which are gitignored) and is what `tests/test_pipeline.py`
runs against. **It is a test fixture, not an analytical dataset** -- every
Gold table, benchmark, model, and Power BI report in this project is built
from the full 58.9M-row / 6-year dataset above, not this sample.

## Known limitations

See `reports/data_limitations.md` for the full, itemized list (suppression
bias with an estimated 17-21% undercount, fee-for-service-only coverage,
beneficiary-service-line double-counting, averages-not-totals payment
fields, standardized-vs-actual payment amounts, latest-year-only service
detail in the Power BI layer, the minimum-30-provider benchmarking floor,
and the statistical/non-investigative nature of outlier flags).
