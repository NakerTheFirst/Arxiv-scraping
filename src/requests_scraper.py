"""requests + BeautifulSoup scraper for ArXiv /list index pages."""

import logging
import re
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config import BASE_URL, USER_AGENT, MAX_PAPERS_PER_CATEGORY
from src.utils import (
    clean_text,
    extract_arxiv_id,
    extract_categories,
    parse_listing_header,
    rate_limit,
    build_list_url,
    strip_descriptor,
)

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30  # seconds


class ListScraper:
    """Scrapes paper stubs from ArXiv /list pages using requests + BeautifulSoup."""

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch(self, url: str) -> Optional[BeautifulSoup]:
        """GET *url* and return a BeautifulSoup tree, or None on failure."""
        try:
            response = self._session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return BeautifulSoup(response.text, "html.parser")
        except requests.RequestException as exc:
            logger.error("Failed to fetch %s: %s", url, exc)
            return None


    @staticmethod
    def _parse_paper_entry(dt: Tag, dd: Tag, list_date: str) -> Optional[dict]:
        """Parse one <dt>/<dd> pair into a paper-stub dict."""
        # --- ArXiv ID (from the "Abstract" anchor or its id= attribute) ---
        abs_anchor = dt.find("a", title="Abstract")
        if not abs_anchor:
            return None
        arxiv_id = extract_arxiv_id(abs_anchor.get_text()) or abs_anchor.get("id", "")
        if not arxiv_id:
            return None

        # --- Download links ---
        pdf_anchor = dt.find("a", title="Download PDF")
        html_anchor = dt.find("a", title="View HTML")

        def _abs_href(anchor: Optional[Tag], fallback: str) -> str:
            href = anchor["href"] if anchor else fallback
            return BASE_URL + href if href.startswith("/") else href

        pdf_url = _abs_href(pdf_anchor, f"/pdf/{arxiv_id}")
        html_url = _abs_href(html_anchor, "") if html_anchor else ""

        meta = dd.find("div", class_="meta")
        if not meta:
            return None

        # --- Title (strip "Title:" descriptor span) ---
        title_div = meta.find("div", class_="list-title")
        title = ""
        if title_div:
            # Remove descriptor span to avoid text contamination
            for desc in title_div.find_all("span", class_="descriptor"):
                desc.decompose()
            title = clean_text(title_div.get_text())

        # --- Authors (prefer anchor text; fall back to raw text) ---
        authors_div = meta.find("div", class_="list-authors")
        authors = ""
        if authors_div:
            author_links = authors_div.find_all("a")
            names = (
                [clean_text(a.get_text()) for a in author_links]
                if author_links
                else [clean_text(s) for s in authors_div.get_text().split(",") if s.strip()]
            )
            authors = "; ".join(names)

        # --- Subjects: primary category + cross-listings ---
        subjects_div = meta.find("div", class_="list-subjects")
        primary_category = ""
        cross_list_categories = ""
        if subjects_div:
            for desc in subjects_div.find_all("span", class_="descriptor"):
                desc.decompose()
            primary_category, cross_list = extract_categories(subjects_div.get_text())
            cross_list_categories = "; ".join(cross_list)

        # --- Optional comments field ---
        comments_div = meta.find("div", class_="list-comments")
        comments = ""
        if comments_div:
            comments = strip_descriptor(comments_div.get_text(), "Comments:")

        return {
            "arxiv_id": arxiv_id,
            "title": title,
            "authors": authors,
            "primary_category": primary_category,
            "cross_list_categories": cross_list_categories,
            "comments": comments,
            "pdf_url": pdf_url,
            "html_url": html_url,
            "abs_url": f"{BASE_URL}/abs/{arxiv_id}",
            "list_date": list_date,
        }

    def _parse_list_page(self, soup: BeautifulSoup) -> list[dict]:
        """Extract all paper stubs from a parsed /list page."""
        articles_dl = soup.find("dl", id="articles")
        if not articles_dl:
            logger.warning("No #articles <dl> found on list page")
            return []

        # The first <h3> carries the listing date and entry counts
        first_h3 = articles_dl.find("h3")
        list_date, _, _ = (
            parse_listing_header(first_h3.get_text()) if first_h3 else ("", 0, 0)
        )

        papers: list[dict] = []
        dt_elements = articles_dl.find_all("dt")
        dd_elements = articles_dl.find_all("dd")

        for dt, dd in zip(dt_elements, dd_elements):
            paper = self._parse_paper_entry(dt, dd, list_date)
            if paper:
                papers.append(paper)

        return papers

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scrape_category(
        self,
        category: str,
        date: str = "recent",
        max_papers: Optional[int] = None,
    ) -> list[dict]:
        """Scrape paper stubs for *category* on *date*.

        Handles ArXiv's default 50-entry limit by re-fetching with
        ``show={total}`` when the listing is truncated.
        """
        url = build_list_url(category, date)
        logger.info("Fetching list page: %s", url)

        soup = self._fetch(url)
        if not soup:
            return []

        # Check whether the page is truncated
        dl = soup.find("dl", id="articles")
        header_text = dl.find("h3").get_text() if dl and dl.find("h3") else ""
        _, shown, total = parse_listing_header(header_text)

        if shown and total and shown < total:
            logger.info(
                "Listing truncated (%d of %d); re-fetching with show=%d",
                shown, total, total,
            )
            rate_limit()
            soup = self._fetch(f"{url}?skip=0&show={total}") or soup

        papers = self._parse_list_page(soup)

        if max_papers is not None:
            papers = papers[:max_papers]

        logger.info("Collected %d stubs from %s/%s", len(papers), category, date)
        return papers

    def scrape_all_categories(
        self,
        categories: list[str],
        date: str = "recent",
    ) -> list[dict]:
        """Scrape all *categories*, tagging each record with its source category."""
        all_papers: list[dict] = []
        for i, category in enumerate(categories):
            if i > 0:
                rate_limit()
            papers = self.scrape_category(category, date, MAX_PAPERS_PER_CATEGORY)
            for p in papers:
                p["source_category"] = category
            all_papers.extend(papers)
        return all_papers

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "ListScraper":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
