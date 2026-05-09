"""Pipeline orchestrator.

Execution order
---------------
1. requests + BeautifulSoup  → paper stubs from /list pages (fast)
2. Selenium                  → full /abs records for a sample (rate-limited)
3. Scrapy spider             → independent /list → /abs crawl (async, writes CSV)
4. Merge & deduplicate       → single master DataFrame
5. Save                      → data/papers.csv  +  data/papers.parquet

Run:           python main.py
Smoke-test:    python main.py --test
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from config import (
    CATEGORIES,
    OUTPUT_CSV,
    OUTPUT_DIR,
    OUTPUT_PARQUET,
    SCRAPE_DATE,
    SCRAPY_CSV,
)
from src.requests_scraper import ListScraper
from src.selenium_scraper import AbsScraper
from src.utils import setup_logging

logger = logging.getLogger(__name__)

# Selenium visits abs pages one at a time (15 s crawl delay each).
# Limit to a reasonable sample so the pipeline completes in finite time.
SELENIUM_SAMPLE = 50

# Column order for the final CSV/Parquet
_COLUMN_ORDER = [
    "arxiv_id",
    "title",
    "authors",
    "abstract",
    "primary_category",
    "cross_list_categories",
    "submission_date",
    "comments",
    "doi",
    "pdf_url",
    "html_url",
    "abs_url",
    "submission_history",
    "source_category",
    "list_date",
    "scraped_at",
]

# Fields that must be non-empty for a record to be considered valid
_REQUIRED: dict[str, list[str]] = {
    "requests": ["arxiv_id", "title", "authors", "primary_category", "abs_url"],
    "selenium": ["arxiv_id", "title", "abstract", "submission_date"],
    "scrapy":   ["arxiv_id", "title", "abstract", "authors", "primary_category"],
}


# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------


def _validate_phase(phase: str, df: pd.DataFrame) -> bool:
    """Log per-record PASS/FAIL for *phase* and return True if all pass."""
    required = _REQUIRED.get(phase, [])
    if df.empty:
        logger.error("[%s] FAIL — scraper returned no records", phase.upper())
        return False

    all_ok = True
    for _, row in df.iterrows():
        arxiv_id = row.get("arxiv_id") or "?"
        missing = [
            f for f in required
            if not str(row.get(f, "")).strip()
        ]
        if missing:
            logger.warning(
                "[%s] FAIL %s — missing: %s", phase.upper(), arxiv_id, missing
            )
            all_ok = False
        else:
            logger.info("[%s] PASS %s", phase.upper(), arxiv_id)

    return all_ok


# ---------------------------------------------------------------------------
# Phase runners
# ---------------------------------------------------------------------------


def run_requests_scraper(max_per_category: int | None = None) -> pd.DataFrame:
    """Phase 1 — collect paper stubs from /list pages via requests + BS4."""
    logger.info("--- Phase 1: requests + BeautifulSoup ---")
    with ListScraper() as scraper:
        records = scraper.scrape_all_categories(
            CATEGORIES, date=SCRAPE_DATE, max_papers=max_per_category
        )
    df = pd.DataFrame(records)
    logger.info("Phase 1 complete: %d stubs", len(df))
    return df


def run_selenium_scraper(arxiv_ids: list[str]) -> pd.DataFrame:
    """Phase 2 — enrich a sample of papers via Selenium on /abs pages."""
    logger.info("--- Phase 2: Selenium (%d papers) ---", len(arxiv_ids))
    with AbsScraper() as scraper:
        records = scraper.scrape_papers(arxiv_ids)
    df = pd.DataFrame(records)
    logger.info("Phase 2 complete: %d records", len(df))
    return df


def run_scrapy_spider(max_items: int | None = None) -> pd.DataFrame:
    """Phase 3 — run the Scrapy spider and load its CSV feed output.

    CrawlerProcess is imported here so that Twisted's reactor is only
    initialised after the synchronous scrapers have finished.
    *max_items* sets CLOSESPIDER_ITEMCOUNT when provided (used in test mode).
    """
    logger.info("--- Phase 3: Scrapy spider ---")

    from scrapy.crawler import CrawlerProcess
    from scrapy.settings import Settings

    import src.scrapy_scraper.settings as scrapy_cfg
    from src.scrapy_scraper.spiders.arxiv_spider import ArxivSpider

    settings = Settings()
    settings.setmodule(scrapy_cfg, priority="project")
    if max_items is not None:
        settings.set("CLOSESPIDER_ITEMCOUNT", max_items, priority="cmdline")

    process = CrawlerProcess(settings, install_root_handler=False)
    process.crawl(ArxivSpider, categories=",".join(CATEGORIES), date=SCRAPE_DATE)
    process.start()  # blocks until the crawl finishes

    scrapy_csv = SCRAPY_CSV
    if not scrapy_csv.exists():
        logger.warning("Scrapy feed not found at %s — skipping", scrapy_csv)
        return pd.DataFrame()

    df = pd.read_csv(scrapy_csv, dtype=str).fillna("")
    logger.info("Phase 3 complete: %d records from %s", len(df), scrapy_csv)
    return df


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


def merge_results(
    requests_df: pd.DataFrame,
    selenium_df: pd.DataFrame,
    scrapy_df: pd.DataFrame,
) -> pd.DataFrame:
    """Combine all three DataFrames, highest-priority source first.

    Priority: scrapy (list + abs, complete) > selenium (abs-only, sample)
              > requests (list-only stubs, broadest coverage).

    Deduplication keeps the first occurrence of each arxiv_id, so
    whichever scraper's record arrives first in the concatenated frame wins.
    """
    logger.info("--- Merging results ---")

    frames = [df for df in (scrapy_df, selenium_df, requests_df) if not df.empty]
    if not frames:
        logger.error("All scrapers returned empty results")
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)

    if "arxiv_id" not in combined.columns:
        logger.error("No arxiv_id column in combined frame")
        return combined

    before = len(combined)
    deduped = combined.drop_duplicates(subset="arxiv_id", keep="first")
    logger.info(
        "Deduplication: %d → %d unique papers (removed %d duplicates)",
        before, len(deduped), before - len(deduped),
    )

    present_ordered = [c for c in _COLUMN_ORDER if c in deduped.columns]
    extras = [c for c in deduped.columns if c not in _COLUMN_ORDER]
    deduped = deduped[present_ordered + extras].reset_index(drop=True)

    str_cols = deduped.select_dtypes(include=["object", "string"]).columns
    deduped[str_cols] = deduped[str_cols].apply(lambda s: s.str.strip())

    return deduped


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


def save_output(df: pd.DataFrame) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    logger.info("Saved → %s  (%d rows)", OUTPUT_CSV, len(df))
    df.to_parquet(OUTPUT_PARQUET, index=False)
    logger.info("Saved → %s", OUTPUT_PARQUET)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="ArXiv metadata scraper pipeline")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Smoke-test mode: scrape 3 articles per phase and validate fields",
    )
    args = parser.parse_args()
    test_mode: bool = args.test

    setup_logging()
    OUTPUT_DIR.mkdir(exist_ok=True)

    if test_mode:
        logger.info("=== SMOKE-TEST MODE (3 articles per phase) ===")

    # Phase 1: list scraper
    requests_df = run_requests_scraper(max_per_category=1 if test_mode else None)
    if test_mode:
        requests_ok = _validate_phase("requests", requests_df.head(3))

    # Phase 2: Selenium
    sample_size = 3 if test_mode else SELENIUM_SAMPLE
    arxiv_ids = requests_df["arxiv_id"].dropna().tolist()[:sample_size]
    selenium_df = run_selenium_scraper(arxiv_ids) if arxiv_ids else pd.DataFrame()
    if test_mode:
        selenium_ok = _validate_phase("selenium", selenium_df)

    # Phase 3: Scrapy
    scrapy_df = run_scrapy_spider(max_items=3 if test_mode else None)
    if test_mode:
        scrapy_ok = _validate_phase("scrapy", scrapy_df.head(3))

    # Merge and save
    final_df = merge_results(requests_df, selenium_df, scrapy_df)
    if final_df.empty:
        logger.error("Pipeline produced no output — aborting")
        sys.exit(1)

    save_output(final_df)

    if test_mode:
        logger.info("=== SMOKE-TEST RESULTS ===")
        for phase, ok in [("requests", requests_ok), ("selenium", selenium_ok), ("scrapy", scrapy_ok)]:
            status = "PASS" if ok else "FAIL"
            logger.info("  %-10s %s", phase, status)
        if not all([requests_ok, selenium_ok, scrapy_ok]):
            logger.error("One or more phases failed — check warnings above")
            sys.exit(1)
        logger.info("All phases passed.")
    else:
        logger.info("Done. %d papers saved to %s", len(final_df), OUTPUT_DIR)


if __name__ == "__main__":
    main()
