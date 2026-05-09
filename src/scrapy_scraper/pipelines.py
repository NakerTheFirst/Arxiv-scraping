"""Item pipelines: deduplication and text normalisation."""

import logging
from itemadapter import ItemAdapter

from src.utils import clean_text

logger = logging.getLogger(__name__)


class DeduplicatePipeline:
    """Drop items whose arxiv_id has already been seen in this run."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        arxiv_id = adapter.get("arxiv_id", "")
        if arxiv_id in self._seen:
            logger.debug("Duplicate dropped: %s", arxiv_id)
            from scrapy.exceptions import DropItem
            raise DropItem(f"Duplicate arXiv ID: {arxiv_id}")
        self._seen.add(arxiv_id)
        return item


class CleanTextPipeline:
    """Normalise whitespace in all string fields."""

    _TEXT_FIELDS = (
        "title", "authors", "abstract", "comments",
        "submission_history", "list_date",
    )

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        for field in self._TEXT_FIELDS:
            value = adapter.get(field)
            if isinstance(value, str):
                adapter[field] = clean_text(value)
        return item
