# ArXiv Metadata Scraper

Scrapes paper metadata from [arxiv.org](https://arxiv.org) across configurable CS categories. Built using **requests**, **BeautifulSoup**, **Selenium**, and **Scrapy** in a three-phase pipeline.

## Quick start

```bash
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
python main.py          # full pipeline
python main.py --test   # smoke-test (3 articles per phase)
```

Output is written to `data/{DD-MM-YY-HH-MM}-papers.csv` and `.parquet`.

## Pipeline

| Phase | Tool | Target | Output |
|---|---|---|---|
| 1 | requests + BeautifulSoup | `/list/{category}/{date}` | paper stubs (no abstract) |
| 2 | Selenium (headless Chrome) | `/abs/{id}` × 50 sample | abstract, DOI, submission date |
| 3 | Scrapy | `/list → /abs` full crawl | complete records, written to CSV/JSONL |
| 4 | pandas | — | merged, deduplicated master dataset |

Results are merged with priority: Scrapy > Selenium > requests. Duplicates are dropped on `arxiv_id`.

## Project structure

```
config.py                        — categories, crawl delay, output paths
main.py                          — orchestrator: runs all three phases then merges
src/
  utils.py                       — shared regex, rate limiting, text cleaning
  requests_scraper.py            — Phase 1: requests + BS4, /list pages
  selenium_scraper.py            — Phase 2: Selenium, /abs pages
  scrapy_scraper/
    pipelines.py                 — deduplication pipeline
    spiders/arxiv_spider.py      — Phase 3: async /list → /abs crawl
data/                            — CSV, Parquet, and Scrapy feed output (git-ignored)
notebooks/report.ipynb           — analysis report with EDA
references/                      — sample HTML pages and robots.txt
```

## Configuration

Edit `config.py` to adjust scope:

```python
CATEGORIES = ["cs.AI", "cs.CV", "cs.LG", "cs.CL"]
SCRAPE_DATE = "recent"          # or "YYYY-MM" for a specific month
MAX_PAPERS_PER_CATEGORY = None  # None = no limit
CRAWL_DELAY = 15                # seconds — do not reduce below robots.txt value
```

## Ethical scraping

- `Crawl-delay: 15` from `robots.txt` honoured on every request
- Only allowed paths accessed: `/list`, `/abs`, `/archive`, `/pdf`, `/html`, `/catchup`
- `ROBOTSTXT_OBEY = True` in Scrapy settings
- No PDFs or source files downloaded
