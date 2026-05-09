"""Scrapy Item definitions for ArXiv paper metadata."""

import scrapy


class ArxivPaperItem(scrapy.Item):
    arxiv_id = scrapy.Field()
    title = scrapy.Field()
    authors = scrapy.Field()            # semicolon-joined
    abstract = scrapy.Field()
    primary_category = scrapy.Field()   # e.g. "cs.AI"
    cross_list_categories = scrapy.Field()  # semicolon-joined
    submission_date = scrapy.Field()    # ISO "YYYY-MM-DD"
    comments = scrapy.Field()
    doi = scrapy.Field()
    pdf_url = scrapy.Field()
    html_url = scrapy.Field()
    abs_url = scrapy.Field()
    submission_history = scrapy.Field()
    source_category = scrapy.Field()    # the /list category this came from
    list_date = scrapy.Field()          # human date from the listing header
    scraped_at = scrapy.Field()         # UTC ISO timestamp
