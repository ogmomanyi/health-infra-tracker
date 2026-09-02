"""Generic RSS procurement source adapter.

Designed for official procurement feeds such as development-bank tender feeds.
The feed URL is supplied by configuration rather than hard-coded scraping rules.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

import requests

from ..ingest import stable_event_id


def fetch_feed(url: str, timeout: int = 30) -> list[dict[str, Any]]:
    response = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "Faram-Procurement-Intelligence/1.0"},
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)
    items: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        def text(name: str) -> str:
            node = item.find(name)
            return (node.text or "").strip() if node is not None else ""

        link = text("link")
        items.append({
            "title": text("title"),
            "description": text("description"),
            "source_url": urljoin(url, link),
            "tender_reference": text("guid"),
            "publication_date": text("pubDate"),
        })
    return items


def normalize_notices(records: list[dict[str, Any]], source: str = "RSS") -> list[dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for record in records:
        title = str(record.get("title") or record.get("description") or "").strip()
        reference = str(record.get("tender_reference") or "").strip()
        if not title and not reference:
            continue
        event_id = stable_event_id(source, reference, title)
        normalized[event_id] = {
            "procurement_event_id": event_id,
            "source": source,
            "source_url": record.get("source_url", ""),
            "tender_reference": reference,
            "title": title,
            "buyer": record.get("buyer", ""),
            "country": record.get("country", ""),
            "publication_date": record.get("publication_date", ""),
            "closing_date": record.get("closing_date", ""),
            "equipment_category": record.get("equipment_category", ""),
            "product_family": record.get("product_family", ""),
            "estimated_value": record.get("estimated_value", ""),
            "currency": record.get("currency", ""),
        }
    return list(normalized.values())


__all__ = ["fetch_feed", "normalize_notices"]
