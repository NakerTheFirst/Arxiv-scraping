# Project Context

## Purpose
University webscraping course project. Scrape paper metadata from ArXiv and produce a
clean, analysis-ready dataset. The course requires demonstrating all four major Python
scraping tools — requests, BeautifulSoup, Selenium, and Scrapy — even though ArXiv is
a mostly static site and Selenium is not strictly necessary.

## Target data
- **Source**: arxiv.org — categories cs.AI, cs.CV, cs.LG, cs.CL (configurable in `config.py`)
- **Scope**: one calendar month, set via `SCRAPE_DATE = "YYYY-MM"` (or `"recent"`)
- **Fields**: arxiv_id, title, authors, abstract, primary_category, cross_list_categories,
  submission_date, comments, doi, pdf_url, html_url, abs_url, submission_history,
  source_category, list_date, scraped_at

## Pipeline (`main.py`)
Three scrapers run sequentially; their outputs are merged and deduplicated on `arxiv_id`.

```
Phase 1  requests + BS4   /list/{cat}/{date}  ->  paper stubs (fast, full coverage)
Phase 2  Selenium         /abs/{id}           ->  enriched records for a 50-paper sample
Phase 3  Scrapy spider    /list -> /abs        ->  independent full crawl (async)
         |
Merge: scrapy > selenium > requests  (first occurrence of each arxiv_id wins)
         |
data/{timestamp}-papers.csv + .parquet
```

## Scraper details

| File | Tool | Target | What it collects |
|------|------|--------|-----------------|
| `src/requests_scraper.py` | requests + BS4 | `/list` pages | stubs: id, title, authors, links, categories |
| `src/selenium_scraper.py` | Selenium + BS4 | `/abs` pages | full metadata incl. abstract, date, doi, history |
| `src/scrapy_scraper/spiders/arxiv_spider.py` | Scrapy | `/list` -> `/abs` | complete records via two-step crawl |
| `src/utils.py` | shared | — | regex patterns, rate limiting, text cleaning |

## Pagination (monthly archives)
ArXiv shows 50 entries by default. For `YYYY-MM` dates the total is in
`<div class="paging">` as "Total of N entries"; for `recent` it is in an `<h3>`
as "showing first N of M". Both scrapers detect whichever is present, then
paginate with `?skip=0&show=2000`, `?skip=2000&show=2000`, ... until exhausted.
`MAX_SHOW = 2000` is the largest value ArXiv's `?show=` parameter accepts.

## Robots.txt compliance
- Crawl-delay: 15 s enforced in `utils.rate_limit()`, called between every request
- Allowed paths used: `/list`, `/abs`, `/archive`, `/pdf`, `/html`, `/catchup`
- User-Agent: `Mozilla/5.0 (compatible; academic-research-scraper/1.0)`

## Configuration (`config.py`)
| Variable | Default | Effect |
|----------|---------|--------|
| `CATEGORIES` | `[cs.AI, cs.CV, cs.LG, cs.CL]` | which ArXiv categories to scrape |
| `SCRAPE_DATE` | `"2026-04"` | month or `"recent"` |
| `MAX_PAPERS_PER_CATEGORY` | `None` | per-category cap (None = no limit) |
| `CRAWL_DELAY` | `15` | seconds between requests |

## Key dependencies
```
requests>=2.32        HTTP fetching
beautifulsoup4>=4.12  HTML parsing (used by both requests and Selenium scrapers)
selenium>=4.25        headless Chrome automation
scrapy>=2.12          async crawl framework
pandas>=2.2           DataFrame construction, merge, deduplication
pyarrow>=18.0         Parquet output
lxml>=5.3             fast HTML parser backend
jupyter>=1.1          report notebook
```

## Output files
- `data/{DD-MM-YY-HH-MM}-papers.csv / .parquet` — merged master dataset
- `data/{DD-MM-YY-HH-MM}-scrapy_papers.csv / .jsonl` — raw Scrapy feed
- `notebooks/report.ipynb` — final analysis report

## Running
```
python main.py          # full pipeline
python main.py --test   # smoke-test: 3 articles per phase, validates required fields
```
