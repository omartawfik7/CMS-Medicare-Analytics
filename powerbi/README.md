# Power BI project (PBIP / TMDL)

This folder is a source-controlled Power BI project (`.pbip` + TMDL semantic
model + PBIR report), generated entirely as text files in a cloud sandbox
that has no Power BI Desktop installed. Everything here -- the star schema,
every relationship, every DAX measure -- was authored directly against the
published TMDL/PBIR schema and cross-checked against DuckDB
(`reports/validation_report.md`), but the report's **visuals** have not been
opened/rendered in Desktop, since nothing in this environment can do that.
See "Known risk" at the bottom before you open it.

## What's here

```
powerbi/
├── Medicare Provider Cost and Utilization Intelligence Platform.pbip
├── Medicare Provider Cost and Utilization Intelligence Platform.SemanticModel/
│   └── definition/
│       ├── model.tmdl              # table list
│       ├── expressions.tmdl        # DataFolder parameter (placeholder path -- see below)
│       ├── relationships.tmdl      # 20 relationships, star schema
│       └── tables/*.tmdl           # 14 tables: 6 dims, 8 facts, 47 DAX measures
├── Medicare Provider Cost and Utilization Intelligence Platform.Report/
│   └── definition/
│       ├── report.json
│       └── pages/                  # 7 pages, 55 visuals (see blueprint below)
├── theme/medicare_intelligence_theme.json   # importable custom theme
└── data/                           # Gold exports as Parquet (gitignored -- see below)
```

## How to open this locally

1. **Regenerate the data exports** (gitignored -- too large to commit; see
   the repo root README for the full pipeline). From the repo root:
   ```bash
   python src/ingest_cms.py --years 2018 2019 2020 2021 2022 2023
   python src/build_silver.py
   python src/build_gold.py
   python src/modeling.py                      # optional, populates Model Intelligence
   python src/export_gold_for_powerbi.py
   ```
   This writes `powerbi/data/*.parquet`.

2. **Open** `Medicare Provider Cost and Utilization Intelligence Platform.pbip`
   in Power BI Desktop (November 2023 or later -- TMDL/PBIP support needs to
   be enabled once under *File > Options > Preview features* on older
   builds; recent Desktop has it on by default).

3. **Set the `DataFolder` parameter.** The committed value in
   `expressions.tmdl` (`C:\Data\CMS-Medicare-Analytics\powerbi\data\`) is a
   placeholder, not a real path on any machine -- it exists only so the
   project opens without a missing-parameter error before you've set your
   own. On first open, Desktop will show a "can't find file" data source
   error (expected). Go to *Transform data > Manage Parameters*, set
   `DataFolder` to the absolute path of **this repo's** `powerbi/data/`
   folder on your machine (e.g.
   `C:\Users\you\CMS-Medicare-Analytics\powerbi\data\`, trailing backslash
   included), click **Refresh**.

4. **(Optional) apply the theme**: *View > Themes > Browse for themes*,
   select `theme/medicare_intelligence_theme.json`.

## Known risk: report visuals were not opened in Desktop

The semantic model (tables, columns, relationships, 47 DAX measures) is the
part of this project I could fully self-verify -- every table/column/
relationship name is cross-checked against the actual exported Parquet
schema, and every core aggregate has a matching DuckDB validation check in
`reports/validation_report.md`.

The 55 visual definitions across the 7 report pages (`*.Report/definition/pages/`)
were hand-authored against the public PBIR visual-container schema, but
**never rendered**, because this sandbox has no Power BI Desktop. Power BI
is generally resilient to an individual malformed visual -- the report still
opens and every other visual still works, with the broken one showing an
inline error you can fix in seconds by re-adding it from the Fields pane.
If you hit that on any visual, the exact fields it needs are listed below,
identical to what's encoded in each visual's JSON.

## Page-by-page field reference

Every measure named below is a real DAX measure in the tables under
`definition/tables/*.tmdl` -- none of this is aspirational.

### 1. Overview (`page1_overview`)
- Cards: `[Total Medicare Payments]`, `[Provider Count]`, `[Total Beneficiary Service-Lines]`, `[Total Services]`, `[Payment per Beneficiary]` -- all from `fact_provider_year`
- Line chart: `dim_year[year]` on axis, `fact_provider_year[Total Medicare Payments]` on values
- Bar chart: `dim_specialty[specialty]` on axis, `fact_specialty_year[Specialty Total Payments]` on values, Top N 15
- Map: `dim_geography[state_name]` (location), `fact_state_year[State Total Payments]` (bubble size)

### 2. Provider Intelligence (`page2_provider`)
- Slicer: `dim_provider[provider_name]`
- Table: `dim_provider[provider_name]`, `fact_provider_year[provider_specialty]`, `[provider_state]`, `[Total Medicare Payments]`, `[Total Services]`, `[Total Beneficiary Service-Lines]`, `[Payment per Beneficiary]`, `[Payment per Service]`, `[Specialty Percentile Rank]`, `[Relative Cost Ratio]`
- Line chart: `dim_year[year]` vs `fact_provider_year[Total Medicare Payments]`
- Bar chart (procedure mix): `dim_hcpcs[hcpcs_description]` vs `fact_provider_service_year[Service-Line Payments (Latest Year)]`, Top N 10
- Cards: `[Specialty Percentile Rank]`, `[Relative Cost Ratio]`

### 3. Specialty Intelligence (`page3_specialty`)
- Slicer: `dim_specialty[specialty]`
- Table: specialty rankings (`fact_specialty_year` columns + measures)
- Bar chart: Top 15 specialties by `[Specialty Total Payments]`
- Scatter: X = `[Specialty Payment per Provider]`, Y = `[Specialty Provider Count]`, details = `dim_specialty[specialty]`
- Line chart: `[Specialty Total Payments]` trend by `dim_year[year]`

### 4. Geographic Intelligence (`page4_geography`)
- Cards: `[State Total Payments]`, `[State Provider Count]`
- Map: `dim_geography[state_name]` + `[State Total Payments]`
- Bar chart: Top 15 states by `[State Total Payments]`
- Table: state detail (`fact_state_year` columns + measures)

### 5. Provider Outlier Explorer (`page5_outliers`)
- Text box: outlier disclaimer (static text, matches `[Outlier Methodology Disclaimer]` measure verbatim)
- Slicer: `dim_specialty[specialty]`
- Cards: `[High-Cost Provider Count]`, `[High-Cost Provider Rate]`, `[Benchmarkable Provider Count]`
- Scatter: X = `[Relative Cost Ratio]`, Y = `[Specialty Percentile Rank]`, details = `fact_provider_year[rendering_npi]`, legend = `fact_provider_year[is_high_cost_outlier]`
- Table: flagged providers (`dim_provider[provider_name]`, specialty, state, `payment_per_beneficiary`, benchmark/outlier measures)

### 6. Procedure Intelligence (`page6_procedure`)
- Slicer: `dim_hcpcs[hcpcs_description]`
- Table: procedure detail (`fact_procedure_year` columns + measures)
- Bar chart: Top 15 procedures by `[Procedure Total Payments]`
- Bar chart (specialty mix): `dim_specialty[specialty]` vs `fact_procedure_specialty_mix[Procedure-Specialty Payments (Latest Year)]`
- Bar chart (geography): `dim_geography[state_name]` vs `fact_provider_service_year[Service-Line Payments (Latest Year)]` -- reachable via the `dim_geography -> dim_provider -> fact_provider_service_year` relationship chain

### 7. Model Intelligence (`page7_model`)
- Cards: `[Model 1 MAE]`, `[Model 1 RMSE]`, `[Model 1 R2]`, `[Model 2 Precision]`, `[Model 2 Recall]`, `[Model 2 F1]`, `[Model 2 ROC AUC]`, `[Model 2 PR AUC]` -- all from `dim_model_metrics`, sourced from `reports/model_metrics.json`
- Table: sample predictions from `fact_model_predictions` (actual vs. predicted, both models)

## Star schema

6 dimensions (`dim_year`, `dim_specialty`, `dim_geography`, `dim_provider`,
`dim_hcpcs`, `dim_place_of_service`) + 8 facts (`fact_provider_year`,
`fact_provider_service_year`, `fact_specialty_year`, `fact_state_year`,
`fact_procedure_year`, `fact_procedure_specialty_mix`,
`fact_model_predictions`, plus `dim_model_metrics` as a small disconnected
metrics table). All relationships are single-direction (dimension filters
fact), one active relationship per fact-dimension pair -- see
`relationships.tmdl` for the full list of 20.

`fact_provider_year` carries full 2018-2023 history at the provider grain;
`fact_provider_service_year` and `fact_procedure_specialty_mix` are latest-
year-only by design (see `reports/data_limitations.md`, item 6) to keep the
Import-mode model within a reasonable size for Desktop on typical hardware.
