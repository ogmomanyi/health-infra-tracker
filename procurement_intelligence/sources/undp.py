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


def parse_notice_page(html: str, page_url: str = DEFAULT_URL) -> list[dict[str, Any]]:
    """Extract procurement cards from the public UNDP notice listing."""
    records: dict[str, dict[str, Any]] = {}
    card_pattern = re.compile(
        r"(?is)<(?:article|div)[^>]*(?:class|id)=[\"'][^\"']*(?:notice|tender|procurement)[^\"']*[\"'][^>]*>(.*?)</(?:article|div)>"
    )
    cards = card_pattern.findall(html) or [html]

    for card in cards:
        links = re.findall(r"(?is)<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", card)
        title = ""
        source_url = ""
        for href, raw in links:
            candidate = _clean(raw)
            if len(candidate) >= 12 and any(token in candidate.lower() for token in ("supply", "procurement", "tender", "equipment", "consult", "services", "works")):
                title = candidate
                source_url = urljoin(page_url, href)
                break
        if not title:
            continue

        text = _clean(card)
        patterns = {
            "reference": r"(?:reference|procurement\s*(?:ref(?:erence)?|number)|process)\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{2,})",
            "country": r"country\s*[:#-]?\s*([A-Za-z][A-Za-z .'-]{2,})",
            "closing_date": r"(?:deadline|closing\s*date|submission\s*deadline)\s*[:#-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4})",
            "publication_date": r"(?:posted|posting\s*date|publication\s*date)\s*[:#-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4})",
        }
        values = {field: (_clean(match.group(1)) if (match := re.search(pattern, text, re.I)) else "") for field, pattern in patterns.items()}
        event_id = stable_event_id("UNDP", values["reference"], title)
        records[event_id] = {
            "procurement_event_id": event_id,
            "source": "UNDP",
            "source_url": source_url,
            "tender_reference": values["reference"],
            "title": title,
            "buyer": "United Nations Development Programme",
            "country": values["country"],
            "publication_date": values["publication_date"],
            "closing_date": values["closing_date"],
            "equipment_category": "",
            "product_family": "",
            "estimated_value": "",
            "currency": "",
            "project_reference": "",
            "procurement_stage": "NOTICE",
            "procurement_priority": "",
        }
    return list(records.values())
