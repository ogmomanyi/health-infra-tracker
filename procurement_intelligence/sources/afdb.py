"""African Development Bank procurement source adapter.

AfDB publishes project-related procurement notices and official feeds. The
adapter supports an official RSS/Atom endpoint when supplied, and also
provides a conservative HTML notice-page normalizer for published notice pages.
"""

from __future__ import annotations
from html import unescape
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..evidence import encode_document_urls
from ..http_client import build_session
from ..ingest import stable_event_id

def fetch_page(url: str, timeout: int = 30, session=None) -> str:
    response = (session or build_session()).get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def normalize_notice_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for record in records:
        title = str(record.get("title") or record.get("description") or "").strip()
        reference = str(record.get("tender_reference") or record.get("reference") or "").strip()
        if not title and not reference:
            continue
        source_url = str(record.get("source_url") or "")
        source_record_id = str(
            record.get("source_record_id")
            or reference
            or urlparse(source_url).path.rstrip("/")
        ).strip()
        event_id = stable_event_id("AfDB", source_record_id, title)
        normalized[event_id] = {
            "procurement_event_id": event_id,
            "source": "AfDB",
            "source_url": source_url,
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
            "source_record_id": source_record_id,
            "notice_text": record.get("notice_text", ""),
            "language": record.get("language", ""),
            "document_urls": record.get("document_urls", encode_document_urls([])),
            "detail_fetch_status": record.get("detail_fetch_status", "LISTING_ONLY"),
        }
    return list(normalized.values())


def parse_notice_page(html: str, page_url: str, *, country: str = "") -> list[dict[str, Any]]:
    """Extract conservative notice-card metadata from an AfDB HTML page."""
    records: list[dict[str, Any]] = []
    soup = BeautifulSoup(html or "", "html.parser")
    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "").strip()
        title = " ".join(unescape(anchor.get_text(" ", strip=True)).split())
        if not title or len(title) < 12:
            continue
        lower = title.lower()
        if not any(token in lower for token in ("procurement", "tender", "bid", "supply", "consult", "works", "equipment")):
            continue
        source_url = urljoin(page_url, href)
        if source_url.rstrip("/") == page_url.rstrip("/"):
            continue
        records.append({
            "title": title,
            "source_url": source_url,
            "source_record_id": urlparse(source_url).path.rstrip("/").rsplit("/", 1)[-1],
            "country": country,
            "buyer": "African Development Bank",
            "procurement_stage": "NOTICE",
        })
    return normalize_notice_records(records)
