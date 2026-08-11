# Metric validation: DuckDB (source of truth) vs. Power BI Parquet exports

This sandbox has no Power BI Desktop to execute DAX directly, so validation works in two stages: (1) confirm the Parquet files Power BI will import are byte-for-byte consistent with the DuckDB Gold tables they were copied from, and (2) recompute each core DAX measure's expected result directly against those Parquet files using the same aggregation the measure uses, so there is a documented expected value to check the report against once opened locally.

| Check | DuckDB Gold | Power BI Parquet | Match |
|---|---:|---:|:---:|
| Row count: gold_provider_year vs fact_provider_year.parquet | 6,687,701 | 6,687,701 | PASS |
| Total Medicare Payments: gold_provider_year vs Parquet SUM | 530,356,641,992.88 | 530,356,641,992.88 | PASS |
| Distinct providers: gold_provider_year vs dim_provider.parquet | 1,548,069 | 1,548,069 | PASS |
| [Total Medicare Payments] (all years, all filters cleared) | 530,356,641,992.88 | 530,356,641,992.88 | PASS |
| [Provider Count] (all years) | 1,548,069 | 1,548,069 | PASS |
| [Total Medicare Payments] filtered to source_year = 2023 | 93,721,075,813.28 | 93,721,075,813.28 | PASS |
| [Specialty Total Payments] filtered to specialty = 'Cardiology', year = 2023 | 3,485,495,792.48 | 3,485,495,792.48 | PASS |
| [State Total Payments] filtered to state = 'CA', year = 2023 | 11,525,458,129.84 | 11,525,458,129.84 | PASS |
| [High-Cost Provider Count] (all years) | 688,109 | 688,109 | PASS |
| [Benchmarkable Provider Count] (all years, peer_group_size >= 30) | 6,687,176 | 6,687,176 | PASS |
| [Procedure Total Payments] filtered to a specific HCPCS + year (99213, 2023) | 4,123,102,926.06 | 4,123,102,926.06 | PASS |

**Overall: ALL CHECKS PASS**
