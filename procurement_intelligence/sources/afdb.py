"""African Development Bank procurement source adapter.

AfDB publishes project-related procurement notices and official feeds. The
adapter supports an official RSS/Atom endpoint when supplied, and also
provides a conservative HTML notice-page normalizer for published notice pages.
"""

from __future__ import annotations
from html import unescape
import re
from typing import Any
from urllib.parse import urljoin
import requests

from ..ingest import stable_event_id

DEFAULT_HEADERS = {"User-Agent": "Faram-Procurement-Intelligence/1.0"}


def fetch_page(url: str, timeout: int = 30) -> str:
    response = requests.get(url, timeout=timeout, headers=DEFAULT_HEADERS)
    response.raise_for_status()
    return response.text


def normalize_notice_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for record in records:
        title = str(record.get("title") or record.get("description") or "").strip()
        reference = str(record.get("tender_reference") or record.get("reference") or "").strip()
        if not title and not reference:
            continue
        event_id = stable_event_id("AfDB", reference, title)
        normalized[event_id] = {
            "procurement_event_id": event_id,
            "source": "AfDB",
            "source_url": record.get("source_url", ""),
            "tender_reference": reference,
            "title": title,
            "buyer": record.get("buyer", "") or "African Development Bank",
            "country": record.get("country", ""),
            "publication_date": record.get("publication_date", ""),
            "closing_date": record.get("closing_date", ""),
            "equipment_category": record.get("equipment_category", ""),
            "product_family": record.get("product_family", ""),
            "estimated_value": record.get("estimated_value", ""),
            "currency": record.get("currency", ""),
            "project_reference": record.get("project_reference", ""),
            "procurement_stage": record.get("procurement_stage", ""),
        }
    return list(normalized.values())


def parse_notice_page(html: str, page_url: str, *, country: str = "") -> list[dict[str, Any]]:
    """Extract conservative notice-card metadata from an AfDB HTML page."""
    records: list[dict[str, Any]] = []
    pattern = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
    for href, raw_title in pattern.findall(html):
        title = re.sub(r"<[^>]+>", " ", raw_title)
        title = " ".join(unescape(title).split())
        if not title or len(title) < 12:
            continue
        lower = title.lower()
        if not any(token in lower for token in ("procurement", "tender", "bid", "supply", "consult", "works", "equipment")):
            continue
        records.append({
            "title": title,
            "source_url": urljoin(page_url, href),
            "country": country,
            "buyer": "African Development Bank",
            "procurement_stage": "NOTICE",
        })
    return normalize_notice_records(records)
