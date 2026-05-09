# ArXiv Metadata Scraper
Scrapes paper metadata from [arxiv.org](https://arxiv.org) across four CS categories (`cs.AI`, `cs.CV`, `cs.LG`, `cs.CL`).  
Built using **requests**, **BeautifulSoup**, **Selenium**, and **Scrapy** in a single pipeline.

## Quick start
```bash
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
python main.py
```

Output is written to `data/papers.csv` and `data/papers.parquet`.

## Project structure
```
arxiv-scraping/
├── config.py                        # categories, crawl delay, output paths
├── main.py                          # orchestrator — runs all three scrapers
├── requirements.txt
│
├── src/
│   ├── utils.py                     # shared regex patterns, rate limiting, helpers
│   ├── requests_scraper.py          # requests + BS4 → /list index pages
│   ├── selenium_scraper.py          # Selenium → /abs detail pages
│   └── scrapy_scraper/
│       ├── items.py                 # ArxivPaperItem field definitions
│       ├── pipelines.py             # deduplication + whitespace normalisation
│       ├── settings.py              # Scrapy settings (delay, autothrottle, feeds)
│       └── spiders/
│           └── arxiv_spider.py      # /list → /abs async crawl
│
├── data/                            # scraped output (CSV, Parquet, Scrapy feeds)
└── notebooks/
    └── report.ipynb                 # analysis report with EDA
```

## Pipeline
| Phase | Tool | Target | Output |
|-------|------|--------|--------|
| 1 | requests + BeautifulSoup | `/list/{category}/{date}` | paper stubs (no abstract) |
| 2 | Selenium (headless Chrome) | `/abs/{id}` × 50 sample | abstract, DOI, submission date |
| 3 | Scrapy | `/list → /abs` full crawl | complete records, written to CSV |
| 4 | pandas | — | merged, deduplicated master dataset |

Results are merged with priority: Scrapy > Selenium > requests. Duplicates are dropped on `arxiv_id`.

## Ethical scraping
- `Crawl-delay: 15` from `robots.txt` honoured on every request
- Only `/list`, `/abs`, `/pdf`, `/html` paths accessed (all explicitly allowed)
- `ROBOTSTXT_OBEY = True` in Scrapy settings
- No PDFs or source files downloaded

## Configuration
Edit `config.py` to adjust scope:

```python
CATEGORIES = ["cs.AI", "cs.CV", "cs.LG", "cs.CL"]
SCRAPE_DATE = "recent"          # or "YYYY-MM" for a specific month
MAX_PAPERS_PER_CATEGORY = 200
CRAWL_DELAY = 15                # seconds — do not reduce below robots.txt value
```
