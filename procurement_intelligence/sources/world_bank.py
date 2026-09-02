"""World Bank Procurement API adapter."""

from __future__ import annotations
from typing import Any
import requests
from ..ingest import stable_event_id

DEFAULT_URL = "https://search.worldbank.org/api/procnotices"


def _first(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("procnotices", "procurement", "notices", "results", "documents"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            nested = value.get("records") or value.get("results") or value.get("documents")
            if isinstance(nested, list):
                return [x for x in nested if isinstance(x, dict)]
    return []


def fetch_notices(*, url: str = DEFAULT_URL, country_codes: list[str] | None = None, rows: int = 500, timeout: int = 30) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"format": "json", "rows": rows}
    if country_codes:
        params["countrycode_exact"] = ";".join(code.upper() for code in country_codes)
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return _records(response.json())


def normalize_notices(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for record in records:
        reference = _first(record, "notice_id", "id", "procurement_number", "procurement_reference", "bid_no")
        title = _first(record, "notice_title", "title", "procurement_name", "description", "contract_description")
        if not reference and not title:
            continue
        event_id = stable_event_id("World Bank", reference, title)
        normalized[event_id] = {
            "procurement_event_id": event_id,
            "source": "World Bank",
            "source_url": _first(record, "url", "notice_url", "link", "procurement_url"),
            "tender_reference": reference,
            "title": title,
            "buyer": _first(record, "borrower", "buyer", "agency", "implementing_agency", "organization"),
            "country": _first(record, "country_name", "country", "countryname"),
            "publication_date": _first(record, "publication_date", "published_date", "date_published", "notice_date"),
            "closing_date": _first(record, "deadline", "closing_date", "submission_deadline", "bid_deadline"),
            "equipment_category": _first(record, "sector", "category", "procurement_category"),
            "product_family": _first(record, "procurement_type", "contract_type", "commodity"),
            "estimated_value": record.get("estimated_value", record.get("contract_value", "")),
            "currency": _first(record, "currency", "currency_code"),
        }
    return list(normalized.values())
