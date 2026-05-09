"""ArXiv Scrapy spider.

Crawl pattern:
  /list/{category}/{date}  →  parse paper stubs + follow /abs links
  /abs/{arxiv_id}          →  parse full metadata, yield ArxivPaperItem

CSS selectors are used for structural navigation (Scrapy's native API);
shared utils handle text cleaning and regex-based field extraction.
"""

import sys
import os
from datetime import datetime, timezone
from typing import Iterator

import scrapy
from scrapy.http import Response

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")))

from config import BASE_URL, CATEGORIES
from src.scrapy_scraper.items import ArxivPaperItem
from src.utils import (
    clean_text,
    extract_arxiv_id,
    extract_categories,
    extract_submission_date,
    parse_listing_header,
    build_list_url,
)


class ArxivSpider(scrapy.Spider):
    """Spider that crawls ArXiv listing pages then follows each paper's /abs page."""

    name = "arxiv"
    allowed_domains = ["arxiv.org"]

    def __init__(
        self,
        categories: str | None = None,
        date: str = "recent",
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.date = date
        self.categories = categories.split(",") if categories else CATEGORIES

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def start_requests(self) -> Iterator[scrapy.Request]:
        for category in self.categories:
            url = build_list_url(category, self.date)
            yield scrapy.Request(
                url,
                callback=self.parse_list,
                meta={"source_category": category},
            )

    # ------------------------------------------------------------------
    # List page: parse stubs, handle pagination, follow /abs links
    # ------------------------------------------------------------------

    def parse_list(self, response: Response) -> Iterator[scrapy.Request]:
        header_text = response.css("dl#articles h3::text").get("")
        list_date, shown, total = parse_listing_header(header_text)

        if shown and total and shown < total:
            self.logger.info(
                "Listing truncated (%d/%d); re-fetching all for %s",
                shown, total, response.meta["source_category"],
            )
            full_url = f"{response.url}?skip=0&show={total}"
            yield response.follow(
                full_url,
                callback=self._parse_entries,
                meta={**response.meta, "list_date": list_date},
            )
            return

        yield from self._parse_entries(response, list_date=list_date)

    def _parse_entries(
        self, response: Response, list_date: str = ""
    ) -> Iterator[scrapy.Request]:
        """Yield one /abs Request per paper entry on the listing page."""
        if not list_date:
            header_text = response.css("dl#articles h3::text").get("")
            list_date, _, _ = parse_listing_header(header_text)

        source_category = response.meta.get("source_category", "")

        # XPath: pair each <dt> with its immediately following <dd>
        articles = response.xpath('//dl[@id="articles"]')
        for dt in articles.xpath("dt"):
            # ArXiv ID from the id= attribute of the "Abstract" anchor
            arxiv_id = dt.css('a[title="Abstract"]::attr(id)').get("").strip()
            if not arxiv_id:
                # Fall back to extracting from the link text
                link_text = dt.css('a[title="Abstract"]::text').get("")
                arxiv_id = extract_arxiv_id(link_text) or ""
            if not arxiv_id:
                continue

            # Download links
            pdf_href = dt.css('a[title="Download PDF"]::attr(href)').get("")
            html_href = dt.css('a[title="View HTML"]::attr(href)').get("")

            def abs_url(href: str) -> str:
                return BASE_URL + href if href.startswith("/") else href

            # Quick stub from the <dd> sibling (title, authors, subjects)
            dd = dt.xpath("following-sibling::dd[1]")

            title_parts = dd.xpath(
                './/div[contains(@class,"list-title")]'
                '//text()[not(parent::span[@class="descriptor"])]'
            ).getall()
            title = clean_text("".join(title_parts))

            authors = "; ".join(
                clean_text(a) for a in dd.css("div.list-authors a::text").getall()
            )

            subjects_text = "".join(
                dd.xpath(
                    './/div[contains(@class,"list-subjects")]'
                    '//text()[not(parent::span[@class="descriptor"])]'
                ).getall()
            )
            primary_category, cross_list = extract_categories(subjects_text)

            comments_parts = dd.xpath(
                './/div[contains(@class,"list-comments")]'
                '//text()[not(parent::span[@class="descriptor"])]'
            ).getall()
            comments = clean_text("".join(comments_parts))

            stub = {
                "arxiv_id": arxiv_id,
                "title": title,
                "authors": authors,
                "primary_category": primary_category,
                "cross_list_categories": "; ".join(cross_list),
                "comments": comments,
                "pdf_url": abs_url(pdf_href),
                "html_url": abs_url(html_href),
                "abs_url": f"{BASE_URL}/abs/{arxiv_id}",
                "source_category": source_category,
                "list_date": list_date,
            }

            yield scrapy.Request(
                f"{BASE_URL}/abs/{arxiv_id}",
                callback=self.parse_abs,
                meta={"stub": stub},
            )

    # ------------------------------------------------------------------
    # /abs page: extract full metadata and yield item
    # ------------------------------------------------------------------

    def parse_abs(self, response: Response) -> Iterator[ArxivPaperItem]:
        stub: dict = response.meta.get("stub", {})

        abs_sel = response.css("div#abs")
        if not abs_sel:
            self.logger.warning("No #abs element on %s", response.url)
            return

        # --- Title (XPath excludes descriptor span text) ---
        title_parts = abs_sel.xpath(
            'h1[contains(@class,"title")]'
            '//text()[not(parent::span[@class="descriptor"])]'
        ).getall()
        title = clean_text("".join(title_parts)) or stub.get("title", "")

        # --- Authors ---
        author_names = abs_sel.css("div.authors a::text").getall()
        authors = (
            "; ".join(clean_text(a) for a in author_names)
            or stub.get("authors", "")
        )

        # --- Abstract (XPath excludes descriptor span) ---
        abstract_parts = abs_sel.xpath(
            'blockquote[contains(@class,"abstract")]'
            '//text()[not(parent::span[@class="descriptor"])]'
        ).getall()
        abstract = clean_text("".join(abstract_parts))

        # --- Submission date from dateline ---
        dateline = clean_text(abs_sel.css("div.dateline::text").get(""))
        submission_date = extract_submission_date(dateline) or ""

        # --- Subjects (metatable) ---
        subjects_text = "".join(abs_sel.css("td.subjects *::text").getall())
        primary_category, cross_list = extract_categories(subjects_text)

        # --- Comments ---
        comments = clean_text(
            "".join(abs_sel.css("td.comments::text").getall())
        ) or stub.get("comments", "")

        # --- DOI ---
        doi = clean_text(response.css("a#arxiv-doi-link::text").get(""))

        # --- Download links ---
        pdf_href = response.css("div.full-text a.download-pdf::attr(href)").get("")
        html_href = response.css(
            "div.full-text a#latexml-download-link::attr(href)"
        ).get("")

        def _abs(href: str, fallback: str = "") -> str:
            if not href:
                return fallback
            return BASE_URL + href if href.startswith("/") else href

        # --- Submission history ---
        history_raw = response.css("div.submission-history").xpath(".//text()").getall()
        submission_history = clean_text("".join(history_raw))

        item = ArxivPaperItem(
            arxiv_id=stub.get("arxiv_id", ""),
            title=title,
            authors=authors,
            abstract=abstract,
            submission_date=submission_date,
            primary_category=primary_category or stub.get("primary_category", ""),
            cross_list_categories=(
                "; ".join(cross_list) or stub.get("cross_list_categories", "")
            ),
            comments=comments,
            doi=doi,
            pdf_url=_abs(pdf_href, stub.get("pdf_url", "")),
            html_url=_abs(html_href, stub.get("html_url", "")),
            abs_url=stub.get("abs_url", response.url),
            submission_history=submission_history,
            source_category=stub.get("source_category", ""),
            list_date=stub.get("list_date", ""),
            scraped_at=datetime.now(timezone.utc).isoformat(),
        )
        yield item
