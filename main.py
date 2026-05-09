"""Pipeline orchestrator.

Execution order
---------------
1. requests + BeautifulSoup  → paper stubs from /list pages (fast)
2. Selenium                  → full /abs records for a sample (rate-limited)
3. Scrapy spider             → independent /list → /abs crawl (async, writes CSV)
4. Merge & deduplicate       → single master DataFrame
5. Save                      → data/papers.csv  +  data/papers.parquet

Run:  python main.py
"""

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


# ---------------------------------------------------------------------------
# Phase runners
# ---------------------------------------------------------------------------


def run_requests_scraper() -> pd.DataFrame:
    """Phase 1 — collect paper stubs from /list pages via requests + BS4."""
    logger.info("--- Phase 1: requests + BeautifulSoup ---")
    with ListScraper() as scraper:
        records = scraper.scrape_all_categories(CATEGORIES, date=SCRAPE_DATE)
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


def run_scrapy_spider() -> pd.DataFrame:
    """Phase 3 — run the Scrapy spider and load its CSV feed output.

    CrawlerProcess is imported here so that Twisted's reactor is only
    initialised after the synchronous scrapers have finished.
    """
    logger.info("--- Phase 3: Scrapy spider ---")

    from scrapy.crawler import CrawlerProcess

    import src.scrapy_scraper.settings as scrapy_cfg
    from src.scrapy_scraper.spiders.arxiv_spider import ArxivSpider

    # Build a Scrapy Settings object from our settings module
    from scrapy.settings import Settings
    settings = Settings()
    settings.setmodule(scrapy_cfg, priority="project")

    process = CrawlerProcess(settings)
    process.crawl(ArxivSpider, categories=",".join(CATEGORIES), date=SCRAPE_DATE)
    process.start()  # blocks until the crawl finishes

    scrapy_csv = OUTPUT_DIR / "scrapy_papers.csv"
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

    # Stack in priority order; Scrapy records are most complete
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

    # Reorder columns: known columns first, any extras appended
    present_ordered = [c for c in _COLUMN_ORDER if c in deduped.columns]
    extras = [c for c in deduped.columns if c not in _COLUMN_ORDER]
    deduped = deduped[present_ordered + extras].reset_index(drop=True)

    # Normalise whitespace in all string columns
    str_cols = deduped.select_dtypes(include="object").columns
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
    setup_logging()
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Phase 1: list scraper — broadest coverage, no abstracts
    requests_df = run_requests_scraper()

    # Phase 2: Selenium — abstracts + full metadata for a sample
    arxiv_ids = requests_df["arxiv_id"].dropna().tolist()[:SELENIUM_SAMPLE]
    selenium_df = run_selenium_scraper(arxiv_ids) if arxiv_ids else pd.DataFrame()

    # Phase 3: Scrapy — independent async crawl (list → abs)
    scrapy_df = run_scrapy_spider()

    # Merge and save
    final_df = merge_results(requests_df, selenium_df, scrapy_df)
    if final_df.empty:
        logger.error("Pipeline produced no output — aborting")
        sys.exit(1)

    save_output(final_df)
    logger.info("Done. %d papers saved to %s", len(final_df), OUTPUT_DIR)


if __name__ == "__main__":
    main()
