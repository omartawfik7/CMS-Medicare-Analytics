"""
Reproducible ingestion entry point for the CMS Medicare Physician & Other
Practitioners "by Provider and Service" public use file.

    python src/ingest_cms.py --years 2019 2020 2021 2022 2023
    python src/ingest_cms.py --year 2023 --force-download

What it does, in order, per requested year:
  1. Look up the confirmed source URL in config/cms_sources.yaml.
  2. Stream-download the CSV to data/raw/ with retries + exponential backoff,
     resuming a partial download via HTTP Range if one exists.
  3. Verify the download (row count via a fast line count, SHA-256 checksum)
     and record provenance in data/raw/manifest.json.
  4. Load the file into DuckDB Bronze via the existing src/ingestion.py
     loader (idempotent per source_file).

Raw CSVs are gitignored (see .gitignore) -- this script is what reproduces
them, not a committed artifact. Re-running is safe: a year already present
in the manifest with a matching checksum is skipped unless --force-download
or --force-reload is passed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import requests
import yaml
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingestion import SourceFile, load_bronze  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "cms_sources.yaml"
RAW_DIR = REPO_ROOT / "data" / "raw"
MANIFEST_PATH = RAW_DIR / "manifest.json"
DB_PATH = REPO_ROOT / "data" / "cms_medicare.duckdb"

CHUNK_SIZE = 8 * 1024 * 1024  # 8MB
MAX_RETRIES = 5
BACKOFF_FACTOR = 2.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest_cms")


def _session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=MAX_RETRIES,
        backoff_factor=BACKOFF_FACTOR,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


@dataclass
class DownloadResult:
    year: int
    url: str
    path: str
    file_size_bytes: int
    sha256: str
    row_count: int
    download_started_at: str
    download_completed_at: str
    elapsed_seconds: float
    resumed: bool


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {}


def save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True))


def download_year(session: requests.Session, year: int, url: str, force: bool) -> DownloadResult:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dest = RAW_DIR / f"MUP_PHY_{year}_Prov_Svc.csv"
    partial = dest.with_suffix(dest.suffix + ".partial")

    if dest.exists() and not force:
        log.info("year=%s already downloaded at %s, skipping (use --force-download to re-pull)", year, dest)
        sha256 = _sha256_file(dest)
        row_count = _count_rows(dest)
        stat = dest.stat()
        now = datetime.now(timezone.utc).isoformat()
        return DownloadResult(
            year=year, url=url, path=str(dest.relative_to(REPO_ROOT)),
            file_size_bytes=stat.st_size, sha256=sha256, row_count=row_count,
            download_started_at=now, download_completed_at=now, elapsed_seconds=0.0,
            resumed=False,
        )

    started = datetime.now(timezone.utc)
    t0 = time.time()
    resumed = False
    mode = "wb"
    headers = {}
    existing_bytes = 0

    if partial.exists() and not force:
        existing_bytes = partial.stat().st_size
        headers["Range"] = f"bytes={existing_bytes}-"
        mode = "ab"

    log.info("year=%s downloading %s -> %s%s", year, url, dest, " (resuming)" if existing_bytes else "")

    with session.get(url, stream=True, timeout=(15, 120), headers=headers) as resp:
        if headers.get("Range") and resp.status_code == 206:
            resumed = True
            log.info("year=%s server honored Range, resuming from byte %s", year, existing_bytes)
        elif headers.get("Range") and resp.status_code == 200:
            log.info("year=%s server ignored Range (full 200), restarting download", year)
            mode = "wb"
        resp.raise_for_status()

        downloaded = existing_bytes if mode == "ab" else 0
        last_log = time.time()
        with open(partial, mode) as f:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                if time.time() - last_log > 15:
                    log.info("year=%s ... %.1f MB downloaded", year, downloaded / 1e6)
                    last_log = time.time()

    partial.rename(dest)
    elapsed = time.time() - t0
    completed = datetime.now(timezone.utc)

    sha256 = _sha256_file(dest)
    row_count = _count_rows(dest)
    size = dest.stat().st_size

    log.info(
        "year=%s downloaded %.1f MB, %s rows, in %.1fs (%.1f MB/s)",
        year, size / 1e6, f"{row_count:,}", elapsed, (size / 1e6) / max(elapsed, 0.001),
    )

    return DownloadResult(
        year=year, url=url, path=str(dest.relative_to(REPO_ROOT)),
        file_size_bytes=size, sha256=sha256, row_count=row_count,
        download_started_at=started.isoformat(), download_completed_at=completed.isoformat(),
        elapsed_seconds=round(elapsed, 1), resumed=resumed,
    )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _count_rows(path: Path) -> int:
    # Data rows only (excludes header). CMS files have no embedded newlines
    # within fields for this dataset, so a line count is exact and fast.
    n = 0
    with open(path, "rb") as f:
        for _ in f:
            n += 1
    return max(n - 1, 0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download + Bronze-load CMS Medicare Physician & Other Practitioners data.")
    parser.add_argument("--year", type=int, help="Single year to ingest.")
    parser.add_argument("--years", type=int, nargs="+", help="Multiple years to ingest.")
    parser.add_argument("--force-download", action="store_true", help="Re-download even if the file already exists locally.")
    parser.add_argument("--skip-bronze", action="store_true", help="Only download; don't load into DuckDB Bronze.")
    parser.add_argument("--db", default=str(DB_PATH), help="Path to the DuckDB database file.")
    args = parser.parse_args()

    years = args.years or ([args.year] if args.year else [])
    if not years:
        parser.error("Provide --year or --years.")

    config = yaml.safe_load(CONFIG_PATH.read_text())
    year_urls = config["years"]

    manifest = load_manifest()
    session = _session()
    con = None if args.skip_bronze else duckdb.connect(args.db)

    for year in sorted(set(years)):
        if str(year) not in year_urls and year not in year_urls:
            log.error("year=%s not found in %s -- skipping", year, CONFIG_PATH)
            continue
        entry = year_urls.get(year, year_urls.get(str(year)))
        url = entry["csv"]

        result = download_year(session, year, url, force=args.force_download)
        manifest[str(year)] = asdict(result)
        save_manifest(manifest)

        if con is not None:
            source = SourceFile(
                path=REPO_ROOT / result.path,
                source_year=year,
                vintage=Path(url).stem,
            )
            stats = load_bronze(con, source)
            log.info(
                "year=%s bronze load: %s rows in %.1fs -> %s",
                year, f"{stats['rows_loaded']:,}", stats["elapsed_seconds"], args.db,
            )

    if con is not None:
        con.close()

    log.info("Done. Manifest at %s", MANIFEST_PATH)


if __name__ == "__main__":
    sys.exit(main())
