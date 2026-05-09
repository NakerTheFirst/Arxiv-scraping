from pathlib import Path

BASE_URL = "https://arxiv.org"

# Target categories (configurable)
CATEGORIES = ["cs.AI", "cs.CV", "cs.LG", "cs.CL"]

# "recent" for the latest listing, or "YYYY-MM" for a specific month
SCRAPE_DATE = "recent"

# Maximum papers to collect per category (None = no limit)
MAX_PAPERS_PER_CATEGORY = 200

# Crawl-delay from robots.txt (seconds)
CRAWL_DELAY = 15

OUTPUT_DIR = Path("data")
OUTPUT_CSV = OUTPUT_DIR / "papers.csv"
OUTPUT_PARQUET = OUTPUT_DIR / "papers.parquet"

USER_AGENT = "Mozilla/5.0 (compatible; academic-research-scraper/1.0)"

ALLOWED_PATHS = ["/list", "/abs", "/archive", "/pdf", "/html", "/catchup"]

SELENIUM_HEADLESS = True
SELENIUM_TIMEOUT = 15  # seconds
