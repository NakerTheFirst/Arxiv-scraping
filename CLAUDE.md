# CLAUDE.md
## Why
University webscraping course project. Scrape ArXiv paper metadata to build a structured dataset.
The project must demonstrate proficiency with: requests, BeautifulSoup, Selenium, Scrapy, and Python regex.
All four scraping tools are mandatory - ArXiv is mostly static, so Selenium is used by design to meet requirements, not out of necessity.

## What
- **Target**: ArXiv paper metadata from categories: cs.AI, cs.CV, cs.LG, cs.CL (configurable in config.py)
- **Data fields**: title, authors, abstract, categories/tags, submission date, PDF/HTML links, citation/cross-list info
- **Output**: structured DataFrame, saved to `data/`
- **Report**: Jupyter notebook in `notebooks/report.ipynb`

## Project structure
```
src/
  requests_scraper.py       # requests + BS4 - scrapes /list index pages
  selenium_scraper.py       # Selenium - scrapes individual /abs pages
  scrapy_scraper/           # Scrapy spider - large-scale crawl
  utils.py                  # shared regex patterns, helpers, rate limiting
config.py                   # categories, date ranges, crawl delay, output paths
main.py                     # orchestrator - runs pipeline end to end
data/                       # scraped output (CSV/parquet)
requirements.txt            # required packages file
notebooks/report.ipynb      # final report
```

## How
- Python 3.13, pip + venv
- Respect `Crawl-delay: 15` from robots.txt on every request
- Respect Disallow rules - only scrape allowed paths (/list, /abs, /archive, /pdf, /html)
- Categories and scraping scope are configured via `config.py` for future extensibility
- Use British English in comments, variable names, and documentation
- Run: `python main.py`

## Constraints
- Individual project - no shared code with other students
- Final submission: ZIP with code, dataset in .csv format, README.txt, requirements.txt, legal_proof.txt
- Graded on: technical correctness, efficiency, data readiness, report clarity, and relative ambition vs other students
