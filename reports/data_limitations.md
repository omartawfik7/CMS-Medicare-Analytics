# Known data limitations

This project uses exactly one CMS public use file -- **Medicare Physician &
Other Practitioners - by Provider and Service** -- across six years
(2018-2023). Every number in this repo inherits that file's real, documented
limitations. None of these are pipeline bugs; they are properties of the
source data, and every downstream table/measure/report page that touches
them carries a comment pointing back here.

## 1. Suppression (privacy threshold)

CMS omits any (rendering NPI, HCPCS code, place of service) row where fewer
than 11 unique beneficiaries received that service from that provider that
year. Suppressed rows are **not present with nulled fields** -- they are
entirely absent from the file. This means:

- Provider-level sums (`provider_total_services`, `provider_total_medicare_payment`
  in `gold_provider_year`) systematically **undercount** providers with many
  low-volume service lines, more so than providers with fewer, larger lines.
- This is a non-random bias correlated with practice pattern, not measurement
  noise -- independent audits comparing this file to CMS's own provider-level
  summary file estimate a 17-21% undercount from suppression alone.
- `n_near_suppression_lines` (Gold) and `is_near_suppression_threshold`
  (Silver) flag service lines with `total_beneficiaries < 11`+small margin,
  as a proxy for "this provider likely has additional suppressed volume,"
  without fabricating a value for what was suppressed.

## 2. Fee-for-service only

This file covers **Original Medicare (Part B fee-for-service) claims only**.
Medicare Advantage (Part C) enrollees -- more than half of all Medicare
beneficiaries nationally by 2023 -- are entirely absent, and MA enrollment
share varies sharply by state and market, so state/geographic comparisons in
this project reflect FFS utilization patterns, not total Medicare
utilization, and that gap itself varies by geography.

## 3. Beneficiary counts are service-line counts, not unique patients

`Tot_Benes` (source) / `total_beneficiaries` (Silver) is the count of unique
beneficiaries **for that one service line**. Summing it across a provider's
many service lines (`provider_total_beneficiaries` in Gold) counts a
beneficiary once per distinct service they received, not once per provider.
A primary care provider who sees the same 500 patients for both an office
visit and a wellness exam will show ~1,000 "beneficiary" incidents, not 500.
This project always labels this field "beneficiary service-lines" or
similar, never "unique patients" or "beneficiaries served," and does not
compare it to CMS's separate by-Provider summary file (which does report
true unique beneficiaries per provider, at a coarser grain this project
doesn't use).

## 4. Averages, not totals, for payment fields

`Avg_Sbmtd_Chrg`, `Avg_Mdcr_Alowd_Amt`, `Avg_Mdcr_Pymt_Amt`,
`Avg_Mdcr_Stdzd_Amt` are per-service averages as published by CMS.
`est_total_medicare_payment` (and everything built on it) is a derived
`total_services x avg_payment` multiply-through, which inherits whatever
rounding is already baked into CMS's published averages. This is standard
practice for this file (there is no published per-line total), but it means
totals are estimates, not ledger-exact sums.

## 5. Standardized vs. actual payment amounts

`Avg_Mdcr_Stdzd_Amt` (imported to Silver but not used as the primary payment
figure in Gold) removes geographic payment-rate adjustments CMS applies via
the physician fee schedule; `Avg_Mdcr_Pymt_Amt` (used throughout this
project) does not. This project uses actual payment amounts everywhere,
which means geographic and state-level comparisons partly reflect Medicare's
own geographic fee-schedule adjustments, not only utilization differences.
This is a deliberate choice (see `reports/design_decisions.md`) since the
business question is actual program spending, not utilization alone -- but
it means a state with a higher fee-schedule locality factor will show higher
per-service payments even at identical utilization.

## 6. Latest-year-only service-line detail in the Power BI layer

`gold_provider_service_year` / `fact_provider_service_year` (the HCPCS x
provider x place-of-service grain) is exported for the **most recent loaded
year only** (currently 2023), not all six years. Multi-year history is
still fully available at the pre-aggregated provider/specialty/state/
procedure grain. This is a deliberate BI-layer scale decision, not a data
gap in DuckDB -- see the header comment in
`sql/gold/02_gold_provider_service_year.sql`.

## 7. Specialty peer-group minimum size

Percentile/median/IQR/robust-z benchmarking (`gold_provider_benchmark`,
`gold_provider_outlier`) requires >= 30 providers in a (specialty, year)
cell (`benchmark_reliable`). Specialties below that threshold are excluded
from benchmarking rather than compared on an unstable base or folded into an
invented broader specialty grouping that doesn't exist in the source data
(`Rndrng_Prvdr_Type` is a flat list of 104 specialty labels with no CMS-
published hierarchy). See `reports/design_decisions.md`, item 5.

## 8. Outlier flags are statistical, not investigative

`is_high_cost_outlier` and the underlying percentile/IQR/robust-z flags
describe **statistical distance from specialty peers**, computed from
aggregate claims summaries with no clinical, case-mix-severity, or audit
data behind them. They cannot and do not indicate fraud, waste, abuse, or
improper billing -- see the disclaimer carried on every outlier-facing table,
measure, and report page.
