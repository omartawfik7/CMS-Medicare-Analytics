# Bronze layer

Bronze loading is done in `src/ingestion.py` (Python + DuckDB's `read_csv`),
not hand-written SQL, because it's a 1:1 structural load: same columns,
all-VARCHAR, plus four provenance columns (`source_year`, `source_file`,
`source_vintage`, `ingested_at`). There's no transformation logic to
express in SQL at this stage -- that starts in `sql/silver/`.

This directory is kept (per the intended repo structure) for future cases
where a source needs pre-Silver SQL-level reshaping before it's uniform
enough to hand to a single Python loader (e.g. if a differently-shaped
CMS file, such as the by-Provider summary file, is added later).
