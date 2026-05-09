"""Scrapy settings for the ArXiv spider.

These are also passed programmatically via CrawlerProcess in main.py,
so changing values here and there are both valid.
"""

import sys
import os

# Make project root importable when Scrapy loads this module directly
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config import (  # noqa: E402
    CRAWL_DELAY,
    SCRAPY_CSV,
    SCRAPY_JSONL,
    USER_AGENT,
)

BOT_NAME = "arxiv_scraper"
SPIDER_MODULES = ["src.scrapy_scraper.spiders"]
NEWSPIDER_MODULE = "src.scrapy_scraper.spiders"

# --- Politeness ---
ROBOTSTXT_OBEY = True
USER_AGENT = USER_AGENT
DOWNLOAD_DELAY = CRAWL_DELAY
RANDOMIZE_DOWNLOAD_DELAY = True   # actual delay ∈ [0.5×, 1.5×] DOWNLOAD_DELAY
CONCURRENT_REQUESTS = 1
CONCURRENT_REQUESTS_PER_DOMAIN = 1

# AutoThrottle adjusts delay based on server response time
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = CRAWL_DELAY
AUTOTHROTTLE_MAX_DELAY = 60
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

# --- Pipelines ---
ITEM_PIPELINES = {
    "src.scrapy_scraper.pipelines.DeduplicatePipeline": 100,
    "src.scrapy_scraper.pipelines.CleanTextPipeline": 200,
}

# --- Feed exports ---
FEEDS = {
    str(SCRAPY_CSV): {
        "format": "csv",
        "overwrite": True,
        "encoding": "utf-8",
    },
    str(SCRAPY_JSONL): {
        "format": "jsonlines",
        "overwrite": True,
        "encoding": "utf-8",
    },
}

# Silence overly verbose Scrapy loggers in normal operation
LOG_LEVEL = "INFO"

# Disable default headers that could leak internal info
DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en",
}
