"""Shared utilities: regex patterns, rate limiting, and data-cleaning helpers."""

import logging
import re
import time
from datetime import datetime
from typing import Optional

from config import CRAWL_DELAY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

# ArXiv paper ID, e.g. "2605.06651" or "arXiv:2605.06651v2"
ARXIV_ID_RE = re.compile(r'\b(\d{4}\.\d{4,5})(?:v\d+)?\b')

# Submission date from /abs dateline, e.g. "[Submitted on 7 May 2026]"
SUBMISSION_DATE_RE = re.compile(
    r'\[(?:Submitted|submitted)\s+on\s+(\d{1,2}\s+\w+\s+\d{4})\]'
)

# Version number suffix, e.g. "v3"
VERSION_RE = re.compile(r'v(\d+)$')

# ArXiv category code, e.g. "cs.AI", "math.CO", "stat.ML"
CATEGORY_CODE_RE = re.compile(r'\b([a-z]+\.[A-Z]{2,})\b')

# Collapse any run of whitespace (including newlines) to a single space
WHITESPACE_RE = re.compile(r'\s+')

# DOI pattern, e.g. "10.48550/arXiv.2605.06651"
DOI_RE = re.compile(r'10\.\d{4,}/\S+')

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def rate_limit() -> None:
    """Pause execution to honour the Crawl-delay from robots.txt."""
    logger.debug("Rate limiting: sleeping %ds", CRAWL_DELAY)
    time.sleep(CRAWL_DELAY)


# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------


def clean_text(text: str) -> str:
    """Collapse whitespace and strip surrounding space from a string."""
    return WHITESPACE_RE.sub(' ', text).strip()


def strip_descriptor(text: str, descriptor: str) -> str:
    """Remove a leading HTML descriptor label (e.g. 'Title:') from text."""
    cleaned = clean_text(text)
    if cleaned.startswith(descriptor):
        cleaned = cleaned[len(descriptor):].strip()
    return cleaned


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------


def extract_arxiv_id(text: str) -> Optional[str]:
    """Return the first arXiv ID found in *text*, or None."""
    match = ARXIV_ID_RE.search(text)
    return match.group(1) if match else None


def extract_submission_date(dateline: str) -> Optional[str]:
    """Parse an ISO date string from a /abs dateline, e.g. '2026-05-07'."""
    match = SUBMISSION_DATE_RE.search(dateline)
    if not match:
        return None
    raw = match.group(1)
    try:
        return datetime.strptime(raw, "%d %B %Y").strftime("%Y-%m-%d")
    except ValueError:
        return clean_text(raw)


def parse_authors(authors_text: str) -> list[str]:
    """Split a comma-delimited author string into a cleaned list of names."""
    return [clean_text(a) for a in authors_text.split(',') if clean_text(a)]


def extract_categories(subjects_text: str) -> tuple[str, list[str]]:
    """Return (primary_code, [cross_list_codes]) from a subjects string.

    Example input: "Artificial Intelligence (cs.AI); Computer Vision (cs.CV)"
    Returns: ("cs.AI", ["cs.CV"])
    """
    codes = CATEGORY_CODE_RE.findall(subjects_text)
    if not codes:
        return ("", [])
    return (codes[0], codes[1:])


def extract_doi(text: str) -> Optional[str]:
    """Return the first DOI found in *text*, or None."""
    match = DOI_RE.search(text)
    return match.group(0) if match else None


def build_abs_url(arxiv_id: str) -> str:
    """Construct the canonical /abs URL for a given arXiv ID."""
    return f"https://arxiv.org/abs/{arxiv_id}"


def build_pdf_url(arxiv_id: str) -> str:
    """Construct the canonical /pdf URL for a given arXiv ID."""
    return f"https://arxiv.org/pdf/{arxiv_id}"


# /list page h3, e.g. "Fri, 8 May 2026 (showing first 50 of 355 entries )"
_LISTING_COUNT_RE = re.compile(r'showing first (\d+) of (\d+)')
_LISTING_DATE_RE = re.compile(r'([A-Z][a-z]+,\s+\d{1,2}\s+[A-Z][a-z]+\s+\d{4})')


# ArXiv only accepts these values for the ?show= query parameter
_VALID_SHOW = (25, 50, 100, 250, 500, 1000, 2000)


def snap_show(total: int) -> int:
    """Return the smallest valid ArXiv ?show= value that covers *total* entries."""
    for v in _VALID_SHOW:
        if v >= total:
            return v
    return _VALID_SHOW[-1]


def parse_listing_header(h3_text: str) -> tuple[str, int, int]:
    """Parse a /list h3 header into (date_str, shown, total).

    ``shown == total`` (or both zero) means the page is not truncated.
    """
    date_m = _LISTING_DATE_RE.search(h3_text)
    date_str = date_m.group(1) if date_m else clean_text(h3_text)
    count_m = _LISTING_COUNT_RE.search(h3_text)
    if count_m:
        return date_str, int(count_m.group(1)), int(count_m.group(2))
    return date_str, 0, 0


def build_list_url(category: str, date: str = "recent") -> str:
    """Construct a /list URL for *category* and *date*.

    *date* can be "recent", "new", or "YYYY-MM".
    """
    return f"https://arxiv.org/list/{category}/{date}"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with a human-readable format."""
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=level,
    )
