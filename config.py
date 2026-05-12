from datetime import datetime
from pathlib import Path

BASE_URL = "https://arxiv.org"

# Target categories (configurable)
CATEGORIES = ["cs.AI", "cs.CV", "cs.LG", "cs.CL"]

# "recent" for the latest listing, or "YYYY-MM" for a specific month
SCRAPE_DATE = "2026-04"

# Maximum papers to collect per category (None = no limit)
MAX_PAPERS_PER_CATEGORY = None

# Crawl-delay from robots.txt (seconds)
CRAWL_DELAY = 15

OUTPUT_DIR = Path("data")

_RUN_TS = datetime.now().strftime("%d-%m-%y-%H-%M")

OUTPUT_CSV = OUTPUT_DIR / f"{_RUN_TS}-papers.csv"
OUTPUT_PARQUET = OUTPUT_DIR / f"{_RUN_TS}-papers.parquet"
SCRAPY_CSV = OUTPUT_DIR / f"{_RUN_TS}-scrapy_papers.csv"
SCRAPY_JSONL = OUTPUT_DIR / f"{_RUN_TS}-scrapy_papers.jsonl"

USER_AGENT = "Mozilla/5.0 (compatible; academic-research-scraper/1.0)"

ALLOWED_PATHS = ["/list", "/abs", "/archive", "/pdf", "/html", "/catchup"]

SELENIUM_HEADLESS = True
SELENIUM_TIMEOUT = 15  # seconds
