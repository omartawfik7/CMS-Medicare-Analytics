# Medicare Provider Cost & Utilization Intelligence Platform

An end-to-end healthcare analytics platform built on **6 years (2018-2023)
of real, national CMS Medicare Physician & Other Practitioners claims-summary
data** -- 58.9M service-line records, 1.55M providers, 104 specialties, 63
states/territories, 7,809 procedure codes, $530B in Medicare payments.
Bronze -> Silver -> Gold in DuckDB, specialty-adjusted statistical
benchmarking, responsible outlier detection, two ML models with real
temporal-holdout metrics, and a source-controlled Power BI semantic model +
report (PBIP/TMDL/PBIR).

## Business problem

What drives geographic and provider-level variation in Medicare utilization
and spending, and can high-cost patterns be identified and predicted in a
way that's statistically defensible and fair across specialties? This
project answers that as if supporting a CMS leadership team, a payer, or a
healthcare analytics organization deciding where to focus cost-containment
and quality review efforts -- using exclusively **public, aggregate CMS
claims-summary data** (provider x service x year statistics), never
individual patient records, EHR data, or PHI of any kind.

## Official CMS data source

**Medicare Physician & Other Practitioners - by Provider and Service**,
published by CMS's Office of Enterprise Data and Analytics.
- Homepage: https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners/medicare-physician-other-practitioners-by-provider-and-service
- Grain: one row per (rendering NPI, HCPCS/service code, place of service), per calendar year
- License: public domain (U.S. government work)
- Full source URLs, per-year vintages, and verification notes: `config/cms_sources.yaml` and `data/README.md`

## Data acquisition

Downloaded directly and programmatically from `data.cms.gov`'s bulk CSV
endpoints via `src/ingest_cms.py` -- streaming download with retries +
exponential backoff, resumable via HTTP Range, SHA-256 checksum, row-count
verification, and full provenance recorded in `data/raw/manifest.json`
(source URL, download timestamp, file size, row count, checksum, per year).
No manual copy-paste, no third-party mirrors.

```
Year   Rows        Size      Download time
2018   9,961,865   3.13 GB   138s
2019   10,140,228  3.18 GB   (resumed from partial)
2020   9,449,361   2.99 GB   45s  (30-67 MB/s sustained)
2021   9,886,177   3.10 GB   105s
2022   9,755,427   3.07 GB   98s
2023   9,660,647   3.06 GB   103s
-----------------------------------
Total  58,853,705  ~18.4 GB
```

## Dataset scale: before and after

The repository previously shipped only a **37-row committed sample**
(12 providers, 31 HCPCS codes, 11 specialties -- pulled live from CMS's own
API for schema validation, real but tiny). That fixture is still committed
(`data/raw/sample_mup_phy_provider_service_2023.csv`) and used by the unit
tests, but every analytical table, benchmark, model, and dashboard in this
project is now built from the **full 6-year national dataset**:

| | Sample fixture | Full dataset (this project) |
|---|---:|---:|
| Rows | 37 | 58,853,705 |
| Years | 1 (2023) | 6 (2018-2023) |
| Providers | 12 | 1,548,069 |
| Specialties | 11 | 104 |
| States/territories | 10 | 63 |
| HCPCS codes | 31 | 7,809 |
| Total Medicare payments | ~$4,600 | $530,356,641,992.88 |
| Total services | 3,437 | 15,069,383,858 |

## Architecture

```
CMS public data (data.cms.gov, bulk CSV, 2018-2023)
    -> src/ingest_cms.py          (download + provenance + Bronze load)
    -> DuckDB Bronze               (bronze_physician_service -- raw grain, all-VARCHAR, provenance columns)
    -> sql/silver/                 (typed, suppression-aware, standardized, 58.9M rows unioned across years)
    -> sql/gold/ (7 SQL scripts)   (provider/specialty/state/procedure aggregates, benchmarking, outliers)
    -> src/features.py, modeling.py, evaluation.py   (2 ML models, temporal validation)
    -> src/export_gold_for_powerbi.py -> powerbi/data/*.parquet
    -> Power BI PBIP/TMDL semantic model + PBIR report (powerbi/)
```

DuckDB was chosen over Databricks/Spark because the full 6-year dataset
(58.9M rows, ~18GB raw) is well within DuckDB's comfort zone on a single
machine -- see `reports/design_decisions.md` for the full reasoning, borne
out here: Bronze load, Silver, and the entire 7-script Gold layer (including
benchmarking and outlier detection over 6.7M provider-years) run in under 3
minutes combined on a 20-core / 31GB sandbox.

## Bronze -> Silver -> Gold

**Bronze** (`bronze_physician_service`): raw grain, all-VARCHAR, +
provenance (`source_year`, `source_file`, `source_vintage`, `ingested_at`).
Idempotent per source file.

**Silver** (`silver_physician_service`, 58,853,705 rows): type coercion,
suppression-aware handling (CMS drops rows below its beneficiary threshold
entirely -- they are not present with nulled fields), standardization
(entity type, place of service, state), grain-uniqueness enforced (0
duplicate `(NPI, HCPCS, place, year)` combinations, verified).

**Gold** (7 tables, built by `sql/gold/01`-`07`, ~51 seconds total):

| Table | Grain | Rows |
|---|---|---:|
| `gold_provider_year` | provider x year | 6,687,701 |
| `gold_provider_service_year` | provider x HCPCS x place, **latest year only** | 9,660,647 |
| `gold_specialty_year` | specialty x year | 610 |
| `gold_state_year` | state x year | 369 |
| `gold_procedure_year` | HCPCS x year | 37,308 |
| `gold_procedure_specialty_mix` | HCPCS x specialty, latest year | 48,165 |
| `gold_provider_benchmark` | provider x year (peer-group stats) | 6,687,621 |
| `gold_provider_outlier` | provider x year (flagged only) | 688,109 |

`gold_provider_service_year` and `gold_procedure_specialty_mix` are
deliberately latest-year-only -- full 58.9M-row service-line detail across 6
years is fine for DuckDB but too large for a portable Power BI Import-mode
model; multi-year trend is still available at every other grain. See
`reports/data_limitations.md`, item 6.

## Provider & specialty analytics

`gold_provider_year` computes, per provider per year: total payments,
services, beneficiary service-lines, distinct HCPCS codes billed, payment
per provider/service/beneficiary, submitted-charge and allowed-amount
totals, payment-to-allowed ratio, and year-over-year change (`$` and `%`)
for both payments and services. `gold_specialty_year` / `gold_state_year`
roll these up with **share-of-national-spend** columns. `gold_procedure_year`
tracks HCPCS-level spend and volume across all 6 years.

## Specialty-adjusted benchmarking

Providers are compared **only within their own specialty and year** --
never across specialties, since a cardiac surgeon and a family physician
have entirely different cost profiles by the nature of their work.

- **Peer group**: `(provider_specialty, source_year)`, computed over
  `payment_per_beneficiary` and `payment_per_service`.
- **Minimum peer-group size: 30 providers.** Below that, percentiles/z-scores
  are statistically unstable, so the cell is marked `benchmark_reliable =
  FALSE` and left un-benchmarked, rather than compared on an unstable base or
  folded into an invented specialty hierarchy that doesn't exist in the CMS
  source data. 6,687,176 of 6,687,701 provider-years (99.99%) clear this bar.
- **Statistics computed**: median, P25, P75, P90, IQR, MAD-based robust
  z-score (`0.6745 x (x - median) / MAD`, Iglewicz & Hoaglin 1993),
  percentile rank, and relative cost ratio (`value / specialty median`).

See `sql/gold/06_gold_provider_benchmark.sql`.

## Outlier detection

Three independent, standard methods flag a provider-year as high-cost, on
`payment_per_beneficiary` within its specialty-year peer group:

1. **Percentile**: at/above the 90th percentile.
2. **IQR (Tukey)**: above `P75 + 1.5 x IQR`.
3. **Robust z-score (MAD)**: above `3.5` (Iglewicz & Hoaglin's standard
   threshold).

688,109 of 6,687,176 benchmarkable provider-years (10.3%) are flagged by at
least one method -- consistent with a ~90th-percentile-anchored definition.
`outlier_methods_triggered_count` records how many of the three methods
agree, so reviewers can distinguish a robust multi-method signal from a
single-method edge case.

> **Statistical outliers represent unusual utilization or cost patterns
> relative to peer providers and do not by themselves indicate fraud,
> waste, abuse, or improper billing.**

This disclaimer is carried on the Gold table, the DAX measure
(`[Outlier Methodology Disclaimer]`), and the Provider Outlier Explorer
report page.

## Machine learning

Both models use **temporal validation** -- trained on 2018-2022, tested on
held-out 2023, never a random shuffle across years (a random split would let
the model see 2023 information indirectly through specialty-year benchmark
medians computed over the whole panel). See `reports/design_decisions.md`
for the full leakage analysis behind every feature-inclusion decision below.

**Model 1 -- Medicare spending prediction** (`XGBRegressor`, log1p target).
Target: `provider_total_medicare_payment`. Features: specialty, state,
entity type, RUCA (rurality), Medicare-participating flag, distinct HCPCS
count, service-line count, peer-group size, prior-year payment and
service-line count -- **excluding** `provider_total_services` and
`payment_per_*`, which are near-deterministic components of the target
itself.

| Metric | Value |
|---|---:|
| Train years | 2018-2022 (n = 5,512,349) |
| Test year | 2023 (n = 1,175,272) |
| MAE | $25,712.03 |
| RMSE | $617,042.83 |
| R² | 0.280 |

R² of 0.28 is honest, not tuned to look better -- practice-pattern and
case-mix features alone explain a moderate share of payment variance once
volume-based features are excluded as leakage; the large RMSE-vs-MAE gap
reflects a heavy right tail (a small number of very high-payment
organizational providers).

**Model 2 -- specialty-adjusted high-cost classification** (`XGBClassifier`,
class-weighted). Target: `payment_per_beneficiary >= specialty-year P90`
(the same percentile-method definition as the outlier flag, but scored
against the *full* benchmarkable population, not just the flagged subset).
Features: case-mix/utilization-intensity and geography only --
**excluding** `payment_per_beneficiary`, `payment_per_service`,
`relative_cost_ratio`, and `robust_z`, since those *are* the label's basis.

| Metric | Value |
|---|---:|
| Train years | 2018-2022 (n = 5,512,008) |
| Test year | 2023 (n = 1,175,168) |
| Positive rate (test) | 10.0% |
| Precision | 0.353 |
| Recall | 0.853 |
| F1 | 0.499 |
| ROC-AUC | 0.925 |
| PR-AUC | 0.677 |

ROC-AUC of 0.925 using only case-mix, utilization-intensity, and geography
features (no payment amounts) shows real, non-circular predictive signal.
Precision at the default 0.5 threshold is moderate (many false positives at
high recall) -- expected given the deliberately non-circular feature set;
threshold tuning is a documented future enhancement, not a hidden result.

Full metrics, feature lists, and the exact label definition:
`reports/model_metrics.json`. Feature importance plots:
`reports/figures/model{1,2}_feature_importance.png`.

## Power BI (PBIP / TMDL / PBIR)

A complete, source-controlled Power BI project in `powerbi/` -- star schema
(6 dimensions, 8 facts, 20 relationships), 47 DAX measures across
Core/Trends/Benchmarking/Outliers/Model display folders, a 7-page report
(55 visuals), and a custom theme. Built entirely as TMDL/PBIR text files in
this sandbox (no Power BI Desktop available here) and cross-validated
against DuckDB (below) -- see **`powerbi/README.md`** for exact opening
instructions, the star schema diagram, and a full field-by-field blueprint
for every visual on every page (useful if any individual visual needs a
30-second manual fix in Desktop, since none of them could be rendered here
to confirm).

**Pages**: Overview, Provider Intelligence, Specialty Intelligence,
Geographic Intelligence, Provider Outlier Explorer, Procedure Intelligence,
Model Intelligence.

## Validation

`src/validate_metrics.py` cross-checks every core aggregate two ways: (1)
DuckDB Gold tables vs. the exact Parquet files Power BI imports (proves the
export didn't drop/duplicate/truncate anything), and (2) recomputes each
DAX measure's expected result directly so there's a documented number to
check the live report against. **All 11 checks pass** -- see
`reports/validation_report.md`, e.g.:

- Total Medicare Payments (all years): $530,356,641,992.88, DuckDB == Parquet
- Total Medicare Payments (2023 only): $93,721,075,813.28, DuckDB == Parquet
- Distinct providers: 1,548,069, DuckDB == Parquet
- High-Cost Provider Count: 688,109, DuckDB == Parquet

## Data quality findings

- **Zero nulls** on specialty, state, beneficiary count, and payment amount across all 58.9M Silver rows.
- **Zero grain-uniqueness violations** on `(NPI, HCPCS, place, year)`.
- Total payments ($530B/6yr, $93.7B in 2023 alone) are in the right order of magnitude for published Medicare Part B FFS physician spending -- a real sanity check, not just an internal-consistency one.
- See `reports/data_limitations.md` for the 8 known, documented limitations of this CMS file: suppression bias, FFS-only coverage, beneficiary-service-line double-counting, averages-not-totals, standardized-vs-actual payment amounts, latest-year-only service detail, the min-N=30 benchmarking floor, and the statistical (non-investigative) nature of outlier flags.

## CMS suppression

CMS omits any (provider, HCPCS, place-of-service) row with fewer than 11
unique beneficiaries, to protect patient privacy -- entirely, not as a
nulled/masked row. This systematically undercounts providers with many
low-volume service lines. `is_near_suppression_threshold` (Silver) and
`n_near_suppression_lines` (Gold) flag rows/providers near that boundary.
Full detail: `reports/data_limitations.md`, item 1.

## Project structure

```
CMS-Medicare-Analytics/
├── README.md
├── requirements.txt
├── config/cms_sources.yaml              # confirmed CMS URLs, 2018-2023
├── data/
│   ├── README.md                         # sources, schema, limitations
│   ├── raw/                               # gitignored full CSVs + manifest.json (provenance)
│   │   └── sample_mup_phy_provider_service_2023.csv   # committed 37-row real sample (tests only)
│   └── cms_medicare.duckdb                # gitignored, ~9GB, regenerate via pipeline below
├── sql/
│   ├── bronze/README.md
│   ├── silver/silver_physician_service.sql
│   └── gold/01_gold_provider_year.sql ... 07_gold_provider_outlier.sql
├── src/
│   ├── ingest_cms.py                      # download + provenance + Bronze load
│   ├── ingestion.py                       # Bronze loader (used by ingest_cms.py and tests)
│   ├── build_silver.py
│   ├── build_gold.py
│   ├── features.py                        # ML feature construction, leakage-safe
│   ├── modeling.py                        # Model 1 + Model 2 training, temporal validation
│   ├── evaluation.py                      # regression/classification metrics
│   ├── export_gold_for_powerbi.py         # Gold -> powerbi/data/*.parquet
│   └── validate_metrics.py                # DuckDB vs. Power BI Parquet cross-checks
├── models/                                 # gitignored trained model artifacts
├── notebooks/                              # 01_eda ... 04_modeling
├── powerbi/
│   ├── *.pbip, *.SemanticModel/, *.Report/  # PBIP/TMDL/PBIR source
│   ├── theme/medicare_intelligence_theme.json
│   ├── data/                                # gitignored Parquet exports
│   └── README.md                            # opening instructions + visual blueprint
├── reports/
│   ├── design_decisions.md                # grain, MVP scope, model targets, leakage risks
│   ├── data_limitations.md                # 8 documented CMS data limitations
│   ├── model_metrics.json                 # real Model 1 + Model 2 metrics
│   ├── validation_report.md               # DuckDB vs. Power BI cross-checks
│   └── figures/                           # feature importance plots
└── tests/test_pipeline.py                 # Bronze->Silver->Gold smoke tests (sample fixture)
```

## Technologies

Python, DuckDB, SQL, pandas, PyArrow/Parquet, scikit-learn, XGBoost, SHAP,
matplotlib/seaborn, Power BI (PBIP/TMDL/PBIR, DAX, Power Query M), Git.

## How to run

```bash
pip install -r requirements.txt --break-system-packages   # or use a venv

# 1. Download real CMS data (6 years, ~18GB, ~10-15 min depending on bandwidth)
python src/ingest_cms.py --years 2018 2019 2020 2021 2022 2023

# 2. Build Silver + Gold (~2 min total)
python src/build_silver.py
python src/build_gold.py

# 3. Train both ML models (~4 min)
python src/modeling.py

# 4. Export Gold -> Power BI Parquet
python src/export_gold_for_powerbi.py

# 5. Validate DuckDB vs. Power BI exports
python src/validate_metrics.py
```

For just the pipeline logic without a multi-GB download, run against the
committed real 37-row sample instead:
```bash
python src/ingestion.py --csv data/raw/sample_mup_phy_provider_service_2023.csv --year 2023 --vintage sample
python src/build_silver.py
python src/build_gold.py
```

## How to refresh with a future CMS release

CMS publishes this file annually with a ~12-15 month lag. When a new year
lands (check `config/cms_sources.yaml`'s source homepage), add the year's
URL there, then:
```bash
python src/ingest_cms.py --year 2024
python src/build_silver.py
python src/build_gold.py
python src/modeling.py
python src/export_gold_for_powerbi.py
```
`ingest_cms.py` is idempotent per year -- re-running an already-loaded year
is a no-op unless `--force-download` is passed.

## How to open the Power BI project

See `powerbi/README.md` for full detail. Short version: run the pipeline
above, open the `.pbip` file in Power BI Desktop (Nov 2023+), set the
`DataFolder` parameter to your local `powerbi/data/` path, Refresh.

## Key insights (from the real 6-year dataset)

- $530.4B in Medicare Part B fee-for-service physician payments across
  2018-2023, $93.7B in 2023 alone, across 1.55M distinct rendering
  providers.
- 10.3% of benchmarkable provider-years (688,109 of 6.69M) are flagged
  high-cost by at least one of three independent statistical methods --
  consistent with, and a useful cross-check on, the P90-anchored
  definition.
- Case-mix, utilization-intensity, and geography features alone (with
  every payment-amount feature deliberately excluded to avoid circularity)
  achieve ROC-AUC 0.925 at identifying specialty-adjusted high-cost
  providers -- real, non-trivial, non-circular predictive signal.
- Spending prediction from practice-pattern features alone (excluding
  volume-based near-leakage features) reaches R² = 0.28 -- a realistic,
  not-inflated result that reflects how much of payment variance is
  genuinely explainable without "cheating" via near-identities of the
  target.

## Limitations

See `reports/data_limitations.md` for the full, itemized list (suppression
bias, FFS-only coverage, beneficiary-service-line double-counting,
averages-not-totals, standardized-vs-actual payment amounts, latest-year-
only service detail in the BI layer, the min-N=30 benchmarking floor, and
the statistical/non-investigative nature of outlier flags). At the project
level: this sandbox has no Power BI Desktop, so the 55 report visuals were
authored against the public schema but never rendered -- see
`powerbi/README.md`'s "Known risk" section. No write access to the GitHub
remote was verified in this session, so all work here is local/staged --
see the handoff commands provided at the end of the working session.

## Future enhancements

- Threshold-tune Model 2's classification cutoff (precision/recall
  trade-off) rather than the default 0.5.
- Add the CMS by-Provider summary file (true unique beneficiary counts,
  demographic mix) as a second source, joined on NPI, to resolve the
  beneficiary-service-line double-counting limitation.
- Multivariate anomaly detection (e.g. isolation forest across the full
  case-mix feature vector) as a fourth, non-percentile-based outlier
  method, for comparison against the three implemented here.
- Extend `gold_provider_service_year`/`gold_procedure_specialty_mix` to a
  rolling 2-3 year window (instead of latest-year-only) if a future Power
  BI target environment can handle the larger Import-mode model, or move
  those tables to DirectQuery/composite mode against DuckDB.
- CI (GitHub Actions) running `pytest` + `src/validate_metrics.py` on
  every push, once GitHub write/Actions access is available.
