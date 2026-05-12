"""Selenium scraper for ArXiv /abs pages.

Selenium is used here to demonstrate browser-automation capability as required
by the course specification. ArXiv /abs pages are static, but Selenium lets us
interact with the rendered DOM and use explicit waits for robustness.
"""

import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config import BASE_URL, SELENIUM_HEADLESS, SELENIUM_TIMEOUT, USER_AGENT
from src.utils import (
    clean_text,
    extract_categories,
    extract_submission_date,
    rate_limit,
)

logger = logging.getLogger(__name__)


class AbsScraper:
    """Scrapes full paper metadata from ArXiv /abs pages using Selenium + BS4."""

    def __init__(self, driver: Optional[webdriver.Chrome] = None) -> None:
        if driver is not None:
            self._driver = driver
            self._owns_driver = False
        else:
            self._driver = self._build_driver()
            self._owns_driver = True
        self._wait = WebDriverWait(self._driver, SELENIUM_TIMEOUT)

    # ------------------------------------------------------------------
    # Driver setup
    # ------------------------------------------------------------------

    @staticmethod
    def _build_driver() -> webdriver.Chrome:
        """Construct a Chrome WebDriver with appropriate options.

        Selenium Manager (bundled since selenium 4.6) resolves the matching
        ChromeDriver automatically — no manual driver download required.
        """
        opts = Options()
        if SELENIUM_HEADLESS:
            opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument(f"--user-agent={USER_AGENT}")
        return webdriver.Chrome(options=opts)

    # ------------------------------------------------------------------
    # Page loading
    # ------------------------------------------------------------------

    def _load_abs_page(self, url: str) -> Optional[BeautifulSoup]:
        """Navigate to *url* and return a BS4 tree once #abs is present."""
        try:
            self._driver.get(url)
            # Explicit wait: block until the abstract container is in the DOM
            self._wait.until(
                EC.presence_of_element_located((By.ID, "abs"))
            )
            return BeautifulSoup(self._driver.page_source, "html.parser")
        except TimeoutException:
            logger.error("Timed out waiting for #abs on %s", url)
            return None
        except WebDriverException as exc:
            logger.error("WebDriver error on %s: %s", url, exc)
            return None

    # ------------------------------------------------------------------
    # Core parse method
    # ------------------------------------------------------------------

    def _parse_abs_page(self, soup: BeautifulSoup, arxiv_id: str) -> dict:
        """Extract all metadata fields from a parsed /abs page."""
        abs_div = soup.find("div", id="abs")
        if not abs_div:
            logger.warning("No #abs div found for %s", arxiv_id)
            return {"arxiv_id": arxiv_id}

        title_tag = abs_div.find("h1", class_="title")
        if title_tag:
            # Descriptor span ("Title:") must be removed before get_text()
            for desc in title_tag.find_all("span", class_="descriptor"):
                desc.decompose()
        title = clean_text(title_tag.get_text()) if title_tag else ""

        authors_div = abs_div.find("div", class_="authors")
        if authors_div:
            links = authors_div.find_all("a")
            names = (
                [clean_text(a.get_text()) for a in links]
                if links
                else [s.strip() for s in authors_div.get_text().split(",") if s.strip()]
            )
            authors = "; ".join(names)
        else:
            authors = ""

        bq = abs_div.find("blockquote", class_="abstract")
        if bq:
            for desc in bq.find_all("span", class_="descriptor"):
                desc.decompose()
        abstract = clean_text(bq.get_text()) if bq else ""

        dateline = abs_div.find("div", class_="dateline")
        submission_date = extract_submission_date(dateline.get_text()) if dateline else ""

        subjects_td = abs_div.find("td", class_="subjects")
        if subjects_td:
            primary_category, cross_list = extract_categories(subjects_td.get_text())
            cross_list_categories = "; ".join(cross_list)
        else:
            primary_category, cross_list_categories = "", ""

        comments_td = abs_div.find("td", class_="comments")
        comments = clean_text(comments_td.get_text()) if comments_td else ""

        doi_link = soup.find("a", id="arxiv-doi-link")
        doi = clean_text(doi_link.get_text()) if doi_link else ""

        history_div = soup.find("div", class_="submission-history")
        submission_history = clean_text(history_div.get_text()) if history_div else ""

        pdf_url = ""
        html_url = ""
        full_text_div = soup.find("div", class_="full-text")
        if full_text_div:
            pdf_anchor = full_text_div.find("a", class_="download-pdf")
            if pdf_anchor:
                href = pdf_anchor.get("href", "")
                pdf_url = BASE_URL + href if href.startswith("/") else href
            html_anchor = full_text_div.find("a", id="latexml-download-link")
            if html_anchor:
                href = html_anchor.get("href", "")
                html_url = BASE_URL + href if href.startswith("/") else href

        return {
            "arxiv_id": arxiv_id,
            "title": title,
            "authors": authors,
            "abstract": abstract,
            "submission_date": submission_date or "",
            "primary_category": primary_category,
            "cross_list_categories": cross_list_categories,
            "comments": comments,
            "doi": doi,
            "pdf_url": pdf_url,
            "html_url": html_url,
            "abs_url": f"{BASE_URL}/abs/{arxiv_id}",
            "submission_history": submission_history,
            "source_category": "",
            "list_date": "",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scrape_paper(self, arxiv_id: str) -> dict:
        """Load and fully parse the /abs page for *arxiv_id*."""
        url = f"{BASE_URL}/abs/{arxiv_id}"
        logger.info("Scraping abs page: %s", url)
        soup = self._load_abs_page(url)
        if not soup:
            return {"arxiv_id": arxiv_id}
        return self._parse_abs_page(soup, arxiv_id)

    def scrape_papers(self, arxiv_ids: list[str]) -> list[dict]:
        """Scrape /abs pages for a list of IDs, honouring the crawl delay."""
        results: list[dict] = []
        for i, arxiv_id in enumerate(arxiv_ids):
            if i > 0:
                rate_limit()
            results.append(self.scrape_paper(arxiv_id))
        return results

    def close(self) -> None:
        if self._owns_driver:
            self._driver.quit()

    def __enter__(self) -> "AbsScraper":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
