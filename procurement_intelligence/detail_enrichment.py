"""Fetch and normalize the most relevant procurement notice detail pages."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from .evidence import (
    decode_document_urls,
    discover_document_links,
    encode_document_urls,
    html_text,
)
from .http_client import build_session


HEALTH_PRODUCT_TERMS = (
    "analyzer", "analyser", "autoclave", "blood", "cold chain",
    "diagnostic", "equipment", "freezer", "health", "hospital",
    "laboratory", "medical", "microscope", "patient", "pcr", "reagent",
    "steril", "ultrasound", "vaccine", "ventilator", "x-ray",
)


def _priority(record: dict[str, Any]) -> tuple[int, str]:
    text = " ".join(
        str(record.get(field) or "")
        for field in ("title", "equipment_category", "product_family")
    ).casefold()
    hits = sum(term in text for term in HEALTH_PRODUCT_TERMS)
    return hits, str(record.get("publication_date") or "")


def _language(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    node = soup.find("html")
    if not node:
        return ""
    value = str(node.get("lang") or "").strip()
    return value.split("-", 1)[0].lower()


def enrich_notice_details(
    records: list[dict[str, Any]],
    *,
    max_records: int = 40,
    timeout: int = 30,
    session=None,
    max_text_chars: int = 12000,
) -> list[dict[str, Any]]:
    """Enrich a bounded set of listing records with detail-page evidence.

    Records with the strongest health-product title evidence are fetched first.
    A failed detail request never discards the listing-level notice.
    """
    if max_records <= 0:
        return [dict(record) for record in records]

    client = session or build_session()
    output = [dict(record) for record in records]
    candidates = [
        index for index, record in enumerate(output)
        if str(record.get("source_url") or "").startswith(("http://", "https://"))
        and not str(record.get("notice_text") or "").strip()
    ]
    candidates.sort(key=lambda index: _priority(output[index]), reverse=True)
    selected = set(candidates[:max_records])

    for index in candidates:
        record = output[index]
        if index not in selected:
            record["detail_fetch_status"] = "NOT_SELECTED"
            continue
        try:
            response = client.get(str(record["source_url"]), timeout=timeout)
            response.raise_for_status()
            raw_html = response.text
            extracted = html_text(raw_html)[:max_text_chars]
            discovered = [
                *decode_document_urls(record.get("document_urls")),
                *discover_document_links(raw_html, str(record["source_url"])),
            ]
            record["notice_text"] = extracted
            record["document_urls"] = encode_document_urls(discovered)
            record["language"] = str(record.get("language") or "") or _language(raw_html)
            record["detail_fetch_status"] = "EXTRACTED" if extracted else "EMPTY"
        except Exception:
            record["detail_fetch_status"] = "FAILED"

    return output
