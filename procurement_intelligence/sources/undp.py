"""Public UNDP procurement notice source adapter."""

from __future__ import annotations

from html import unescape
import re
from typing import Any
from urllib.parse import urljoin

import requests

from ..ingest import stable_event_id

DEFAULT_URL = "https://procurement-notices.undp.org/"
DEFAULT_HEADERS = {"User-Agent": "Faram-Procurement-Intelligence/1.0"}


def fetch_page(url: str = DEFAULT_URL, timeout: int = 30) -> str:
    response = requests.get(url, timeout=timeout, headers=DEFAULT_HEADERS)
    response.raise_for_status()
    return response.text


def _clean(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", unescape(value)).strip()


def _extract(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.I)
    return _clean(match.group(1)) if match else ""


def _normalise_country(value: str) -> str:
    value = _clean(value)
    if "/" in value:
        value = value.rsplit("/", 1)[-1]
    return value.strip(" -")


def _normalise_date(value: str) -> str:
    """Return a stable ISO date where the public UNDP format is recognisable."""
    value = _clean(value)
    value = re.sub(r"(\d{1,2}-[A-Za-z]{3}-\d{2})(?:\d{1,2}:\d{2}\s*(?:AM|PM).*)$", r"\1", value, flags=re.I)
    for pattern in (
        r"^(\d{1,2})[-/]([A-Za-z]{3})[-/](\d{2,4})$",
        r"^(\d{1,2})[-/]([A-Za-z]+)[-/](\d{2,4})$",
        r"^(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})$",
    ):
        match = re.match(pattern, value, re.I)
        if not match:
            continue
        day, month, year = match.groups()
        if month.isdigit():
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        try:
            month_num = __import__("datetime").datetime.strptime(month[:3], "%b").month
            year_num = int(year)
            if year_num < 100:
                year_num += 2000
            return f"{year_num:04d}-{month_num:02d}-{int(day):02d}"
        except ValueError:
            pass
    return value


def _record(title: str, source_url: str, text: str, page_url: str) -> dict[str, Any] | None:
    title = _clean(title)
    if len(title) < 12:
        return None
    if not any(token in title.lower() for token in ("supply", "procurement", "tender", "equipment", "consult", "services", "works")):
        return None

    reference = _extract(
        r"(?:ref\.?\s*(?:no\.?|number)?|reference|procurement\s*(?:ref(?:erence)?|number))\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{2,})",
        text,
    )
    country = _normalise_country(
        _extract(r"(?:UNDP\s+Office/Country|country)\s*[:#-]?\s*([^|\n]+?)(?=\s+(?:Procurement\s+Process|Process|Deadline|Posted)\b|$)", text)
    )
    closing = _extract(
        r"(?:deadline|closing\s*date|submission\s*deadline)\s*[:#-]?\s*([^|\n]+?)(?=\s+(?:Posted|Publication|Published)\b|$)",
        text,
    )
    posted = _extract(
        r"(?:posted|posting\s*date|publication\s*date|published)\s*[:#-]?\s*([^|\n]+)$",
        text,
    )

    event_id = stable_event_id("UNDP", reference, title)
    return {
        "procurement_event_id": event_id,
        "source": "UNDP",
        "source_url": source_url or page_url,
        "tender_reference": reference,
        "title": title,
        "buyer": "United Nations Development Programme",
        "country": country,
        "publication_date": _normalise_date(posted),
        "closing_date": _normalise_date(closing),
        "equipment_category": "",
        "product_family": "",
        "estimated_value": "",
        "currency": "",
        "project_reference": "",
        "procurement_stage": "NOTICE",
        "procurement_priority": "",
    }


def parse_notice_page(html: str, page_url: str = DEFAULT_URL) -> list[dict[str, Any]]:
    """Extract notices from the public UNDP listing.

    The public site currently renders notices in a tabular listing with the
    fields Title, Ref No, UNDP Office/Country, Procurement Process, Deadline
    and Posted. The parser also accepts card-style HTML so fixture and future
    site-layout changes remain backwards compatible.
    """
    records: dict[str, dict[str, Any]] = {}

    rows = re.findall(r"(?is)<tr\b[^>]*>(.*?)</tr>", html)
    if rows:
        for row in rows:
            links = re.findall(r"(?is)<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", row)
            for href, raw_title in links:
                record = _record(raw_title, urljoin(page_url, href), _clean(row), page_url)
                if record:
                    records[record["procurement_event_id"]] = record
                    break

    if not records:
        card_pattern = re.compile(
            r"(?is)<(?:article|div)[^>]*(?:class|id)=[\"'][^\"']*(?:notice-card|notice|tender|procurement)[^\"']*[\"'][^>]*>(.*?)</(?:article|div)>"
        )
        cards = card_pattern.findall(html)
        for card in cards:
            links = re.findall(r"(?is)<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", card)
            for href, raw_title in links:
                record = _record(raw_title, urljoin(page_url, href), _clean(card), page_url)
                if record:
                    records[record["procurement_event_id"]] = record
                    break

    return list(records.values())
