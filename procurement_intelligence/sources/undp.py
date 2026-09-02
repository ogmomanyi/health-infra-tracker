"""Public UNDP procurement notice source adapter."""

from __future__ import annotations

from datetime import datetime
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


def _normalise_country(value: str) -> str:
    value = _clean(value)
    if "/" in value:
        value = value.rsplit("/", 1)[-1]
    return value.strip(" -")


def _normalise_date(value: str) -> str:
    """Return a stable ISO date where the public UNDP format is recognisable."""
    value = _clean(value)
    value = re.sub(
        r"(\d{1,2}-[A-Za-z]{3}-\d{2})(?:\d{1,2}:\d{2}\s*(?:AM|PM).*)$",
        r"\1",
        value,
        flags=re.I,
    )
    for pattern in (
        r"^(\d{1,2})[-/]([A-Za-z]{3})[-/](\d{2,4})$",
        r"^(\d{1,2})[-/]([A-Za-z]+)[-/](\d{2,4})$",
        r"^(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})$",
    ):
        match = re.match(pattern, value, re.I)
        if not match:
            continue
        day, month, year = match.groups()
        year_num = int(year)
        if year_num < 100:
            year_num += 2000
        if month.isdigit():
            month_num = int(month)
        else:
            try:
                month_num = datetime.strptime(month[:3], "%b").month
            except ValueError:
                continue
        return f"{year_num:04d}-{month_num:02d}-{int(day):02d}"
    return value


def _build_record(
    title: str,
    source_url: str,
    reference: str,
    country: str,
    closing_date: str,
    publication_date: str,
    page_url: str,
) -> dict[str, Any] | None:
    title = _clean(title)
    if len(title) < 12:
        return None
    if not any(
        token in title.lower()
        for token in ("supply", "procurement", "tender", "equipment", "consult", "services", "works")
    ):
        return None

    event_id = stable_event_id("UNDP", reference, title)
    return {
        "procurement_event_id": event_id,
        "source": "UNDP",
        "source_url": source_url or page_url,
        "tender_reference": _clean(reference),
        "title": title,
        "buyer": "United Nations Development Programme",
        "country": _normalise_country(country),
        "publication_date": _normalise_date(publication_date),
        "closing_date": _normalise_date(closing_date),
        "equipment_category": "",
        "product_family": "",
        "estimated_value": "",
        "currency": "",
        "project_reference": "",
        "procurement_stage": "NOTICE",
        "procurement_priority": "",
    }


def _record_from_card(title: str, source_url: str, text: str, page_url: str) -> dict[str, Any] | None:
    """Parse labelled metadata from card-style notice markup."""
    text = _clean(text)

    def labelled(label_pattern: str, stop_labels: str = "") -> str:
        match = re.search(rf"\b(?:{label_pattern})\b\s*[:#-]?\s*(.*)", text, re.I)
        if not match:
            return ""
        value = match.group(1).strip()
        if stop_labels:
            value = re.split(rf"\s+(?=(?:{stop_labels})\s*[:#-]?\s*)", value, maxsplit=1, flags=re.I)[0]
        return _clean(value)

    reference = labelled(r"reference|ref\.?\s*(?:no\.?|number)?|procurement\s*(?:ref(?:erence)?|number)")
    country = labelled(r"UNDP\s+Office/Country|country", r"Procurement\s+Process|Process|Deadline|Posted|Publication|Published")
    closing = labelled(r"Deadline|closing\s+date|submission\s+deadline", r"Posted|Publication|Published")
    posted = labelled(r"Posted|posting\s+date|publication\s+date|published")
    return _build_record(title, source_url, reference, country, closing, posted, page_url)


def parse_notice_page(html: str, page_url: str = DEFAULT_URL) -> list[dict[str, Any]]:
    """Extract notices from the public UNDP procurement listing.

    The public site currently renders notices in a table with Title, Ref No,
    UNDP Office/Country, Procurement Process, Deadline and Posted columns.
    Card-style parsing is retained as a compatibility fallback.
    """
    records: dict[str, dict[str, Any]] = {}

    rows = re.findall(r"(?is)<tr\b[^>]*>(.*?)</tr>", html)
    for row in rows:
        cells = re.findall(r"(?is)<td\b[^>]*>(.*?)</td>", row)
        if len(cells) < 6:
            continue
        link = re.search(r"(?is)<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", cells[0])
        if not link:
            continue
        href, raw_title = link.groups()
        values = [_clean(cell) for cell in cells[:6]]
        record = _build_record(
            raw_title,
            urljoin(page_url, href),
            values[1],
            values[2],
            values[4],
            values[5],
            page_url,
        )
        if record:
            records[record["procurement_event_id"]] = record

    if not records:
        card_pattern = re.compile(
            r"(?is)<(?:article|div)[^>]*(?:class|id)=[\"'][^\"']*(?:notice-card|notice|tender|procurement)[^\"']*[\"'][^>]*>(.*?)</(?:article|div)>"
        )
        for card in card_pattern.findall(html):
            links = re.findall(r"(?is)<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", card)
            for href, raw_title in links:
                record = _record_from_card(raw_title, urljoin(page_url, href), card, page_url)
                if record:
                    records[record["procurement_event_id"]] = record
                    break

    return list(records.values())
