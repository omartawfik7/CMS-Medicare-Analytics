# Medicare Healthcare Cost & Utilization Intelligence Platform

## Business problem

What factors drive geographic and provider-level variation in Medicare
utilization and spending, and can we identify high-cost patterns and
predict future utilization? This project builds an end-to-end healthcare
analytics platform to answer that question, designed as if supporting a
CMS leadership team, a payer, or a healthcare analytics organization
deciding where to focus cost-containment and quality efforts.

It uses exclusively **public, aggregate CMS claims-summary data** --
provider x service x year statistics, not individual patient records, EHR
data, or PHI of any kind.

## What's here so far (Milestone 1)

- A verified, real CMS data source and schema (see `data/README.md` and
  `reports/design_decisions.md` for how and why).
- A working Bronze -> Silver -> Gold pipeline in DuckDB, tested end-to-end
  against a real 37-row sample pulled live from the CMS API.
- Documented model targets, MVP scope, and leakage risks -- decided *from*
  the measured schema, not assumed in advance.

Not yet built: the full-scale (~9-10M row) ingestion run (blocked in this
environment by network egress restrictions to `data.cms.gov` -- see
`data/README.md` for the exact commands to run it yourself), the ML/
statistical modeling layer, and the dashboard.

## Architecture

```
CMS public data (data.cms.gov)
    -> Python ingestion (src/ingestion.py)
    -> local raw CSV (data/raw/)
    -> DuckDB Bronze (sql/bronze/ -- raw grain, raw types, provenance columns)
    -> SQL Silver (sql/silver/ -- typed, suppression-aware, standardized)
    -> SQL Gold (sql/gold/ -- provider_performance, specialty_benchmarks, ...)
    -> Python/statistical modeling + ML (src/modeling.py, notebooks/)
    -> Tableau/Power BI-ready extracts (dashboard/)
```

DuckDB was chosen over Databricks/Spark because the full multi-year dataset
(~116M rows across 2013-2024) is well within what DuckDB handles locally --
see `reports/design_decisions.md` for the full reasoning. The same
ingestion code scales from the 37-row sample used to validate this repo up
to the full national annual file without modification -- only the input
CSV path changes.

## Data

**Medicare Physician & Other Practitioners - by Provider and Service**,
published by CMS. Grain: one row per (rendering NPI, HCPCS code, place of
service) per calendar year. Full source details, confirmed download URLs,
and known limitations (suppression, FFS-only coverage) are in
`data/README.md`.

## Repository structure

```
cms-medicare-analytics/
├── README.md
├── requirements.txt
├── data/
│   ├── README.md                          # sources, download commands, limitations
│   └── raw/
│       └── sample_mup_phy_provider_service_2023.csv   # real 37-row CMS sample (committed)
├── config/
│   └── cms_sources.yaml                    # confirmed CMS URLs by year
├── notebooks/
│   ├── 01_eda.ipynb
│   ├── 02_feature_engineering.ipynb
│   ├── 03_statistical_analysis.ipynb
│   └── 04_modeling.ipynb
├── src/
│   ├── ingestion.py                        # Bronze loader (implemented, tested)
│   ├── cleaning.py                         # (planned)
│   ├── features.py                         # (planned)
│   ├── modeling.py                         # (planned)
│   └── evaluation.py                       # (planned)
├── sql/
│   ├── bronze/
│   ├── silver/
│   │   └── silver_physician_service.sql    # implemented, tested
│   └── gold/
│       └── gold_provider_performance.sql   # implemented, tested
├── dashboard/
├── tests/
├── reports/
│   └── design_decisions.md                 # grain, MVP scope, model targets, leakage risks
└── docs/
```

## Quickstart

```bash
pip install -r requirements.txt --break-system-packages

# Load the committed real sample into a local DuckDB file:
python src/ingestion.py \
  --csv data/raw/sample_mup_phy_provider_service_2023.csv \
  --year 2023 --vintage "R25_P05_V20_D23 (sample)"

# Run Silver + Gold transforms:
python -c "
import duckdb
con = duckdb.connect('data/cms_medicare.duckdb')
con.execute(open('sql/silver/silver_physician_service.sql').read())
con.execute(open('sql/gold/gold_provider_performance.sql').read())
print(con.execute('SELECT * FROM gold_specialty_benchmarks').fetchdf())
"
```

To run against the full national CY2023 file (or any other year), see the
download command in `data/README.md`, then point `--csv` at that file
instead -- the pipeline code is identical.
