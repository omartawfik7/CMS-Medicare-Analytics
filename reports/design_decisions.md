# Design decisions (based on the confirmed CMS schema and measured scale)

## 1. Can the full dataset be processed locally?

**Yes.** One year is ~9-10M rows / 2-3GB CSV; the full 2013-2024 history is
~116M rows across the provider-and-service grain. DuckDB handles this
comfortably on a laptop (it's routinely used well past 100M rows locally).
**Decision: DuckDB + Python + SQL, no Databricks.** Databricks would add
operational overhead (cluster management, cost) for no processing benefit
at this scale, and would only be worth reconsidering if the project later
joins in something much larger (e.g. full raw NPPES registry + Census
block-group ACS data at national granularity, or moves to multi-year
provider-panel modeling with beneficiary-level linkage).

## 2. Final analytical grain

- **Bronze / Silver**: (rendering NPI, HCPCS code, place of service, year) --
  matches the source file exactly, no aggregation.
- **Gold `provider_performance`**: (rendering NPI, year) -- one row per
  provider per year, the base table for benchmarking and Model 1.
- **Gold `specialty_benchmarks`**: same grain, joined against specialty x
  year medians/percentiles for peer comparison.

Provider-and-service (not provider-only, not geography-only) was chosen
over the two alternative CMS files because it's the only one that lets us
compute *service-level* cost/utilization variation (procedure mix,
HCPCS-level outliers) as well as roll up to provider and geography --
the coarser files can't be disaggregated back down.

## 3. MVP scope: one year vs. multi-year, subset vs. full national

**Start with one year (CY2023, the latest available), full national
volume, not a geographic/specialty subset.**

Reasoning:
- One year avoids the added complexity of year-over-year schema drift and
  panel-construction issues (a provider's NPI can appear/disappear between
  years for reasons unrelated to their actual practice -- retirement,
  re-credentialing, etc.) until the core pipeline and models are proven.
- Full national volume (not a state/specialty subset) is *still* only
  ~9-10M rows -- well within DuckDB's comfort zone -- so there's no
  performance reason to subset, and subsetting would bias specialty
  benchmarks and geographic comparisons, which are core to the business
  question.
- Once Bronze/Silver/Gold and both models are validated on CY2023, add
  years by re-running the *same* ingestion code against each year's CSV
  (`config/cms_sources.yaml` already lists 2018-2023) and unioning in
  Silver -- the schema is stable year over year, so this is additive, not
  a rewrite. That's what `source_year` is threaded through every layer for.

## 4. Model 1: spending/utilization prediction -- exact target

**Target**: `provider_total_medicare_payment` (from `gold_provider_performance`)
-- provider-level aggregate Medicare payment for the year, in dollars.

Rationale: this is the field CMS leadership / a payer would most directly
care about forecasting or explaining, it's continuous, and it's built from
the standardized payment amounts (`Avg_Mdcr_Stdzd_Amt`-derived where
relevant) which control for geographic payment-rate differences, so the
model explains *utilization and practice pattern* differences rather than
just re-discovering that some ZIP codes have higher Medicare fee schedules.

Candidate features: specialty, state/RUCA (rurality), participating
indicator, distinct HCPCS count, service-line count, prior-year payment
(once multi-year data is added) -- deliberately excluding
`provider_total_services` and `payment_per_beneficiary` as direct features
when the target is total payment, since those are near-deterministic
components of the target itself (see leakage risks below).

## 5. Model 2: high-cost/outlier classification -- exact target

**Target**: binary flag, `payment_ratio_to_specialty_median > p90 threshold`
computed *within specialty and year* in `gold_specialty_benchmarks`
(i.e., `payment_per_beneficiary` above the 90th percentile for that
provider's own specialty, that year).

This is deliberately specialty-adjusted and percentile-based rather than an
absolute dollar cutoff, so a cardiac surgeon and a family physician are
never compared on the same scale. It is labeled and documented everywhere
as a **statistical outlier flag**, not a fraud indicator -- CMS's own
published guidance is explicit that utilization outliers can reflect
patient case-mix, specialty sub-focus, or legitimate practice differences,
and this project has no claims-level or audit data that would be needed to
support a fraud determination.

## 6. Leakage risks and target-definition issues to resolve before modeling

1. **Model 1 leakage**: `provider_total_services` and
   `payment_per_beneficiary` are algebraically close to
   `provider_total_medicare_payment` (payment ≈ services × avg payment
   per service). Including them as features would let the model "predict"
   the target from its own near-identity -- they must be excluded or,
   if kept, clearly framed as a decomposition exercise rather than a
   genuine prediction task.
2. **Model 2 circularity**: `payment_ratio_to_specialty_median` *is* the
   basis of the label, by construction. Any feature derived from the same
   payment fields used to build the percentile threshold (e.g.
   `provider_avg_payment_per_service_line`) will trivially separate the
   classes. Real predictive features need to come from case-mix, HCPCS
   composition, geography, and provider attributes that are not simple
   restatements of the payment amount itself.
3. **Suppression-driven bias**: because low-volume service lines are
   omitted below CMS's beneficiary threshold, providers with many
   low-volume, low-cost services will look artificially higher-cost on a
   per-service-line basis than providers with fewer, larger service
   lines -- this is a real confound for both models, not just a data
   nuisance, and should be reported as a limitation on any "high-cost
   outlier" result rather than smoothed over.
4. **Year-over-year panel leakage** (once multi-year data is added): if a
   prior-year payment feature is used to predict current-year payment,
   train/test splits must be time-ordered (train on earlier years, test on
   later years), never randomly shuffled across years, or the model will
   see future information indirectly through specialty-year benchmark
   medians computed over the whole panel.
5. **Small-N specialties**: some specialties will have very few providers
   nationally in a given year, making specialty-year percentile thresholds
   unstable. Worth a minimum-N floor (e.g. require >= 30 providers per
   specialty-year cell) before using a specialty as its own peer group in
   Model 2, falling back to a broader specialty grouping otherwise.
