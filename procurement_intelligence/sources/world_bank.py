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


def _detail_url(reference: str) -> str:
    if not reference:
        return ""
    return f"https://search.worldbank.org/api/v2/procnotices?format=json&id={reference}"


def normalize_notices(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for record in records:
        reference = _first(
            record,
            "notice_id",
            "id",
            "procurement_number",
            "procurement_reference",
            "bid_no",
        )
        title = _first(
            record,
            "bid_description",
            "notice_title",
            "title",
            "procurement_name",
            "description",
            "contract_description",
        )
        if not reference and not title:
            continue

        event_id = stable_event_id("World Bank", reference, title)
        normalized[event_id] = {
            "procurement_event_id": event_id,
            "source": "World Bank",
            "source_url": _first(record, "url", "notice_url", "link", "procurement_url") or _detail_url(reference),
            "tender_reference": _first(record, "bid_reference", "bid_no", "procurement_number", "procurement_reference", "notice_id", "id"),
            "title": title,
            "buyer": _first(
                record,
                "contact_organization",
                "contact_organization_name",
                "borrower_name",
                "borrower",
                "buyer",
                "agency",
                "implementing_agency",
                "organization",
            ),
            "country": _first(record, "country_name", "country", "countryname", "contact_country"),
            "publication_date": _first(record, "notice_date", "publication_date", "published_date", "date_published"),
            "closing_date": _first(record, "deadline_date", "deadline", "closing_date", "submission_deadline", "bid_deadline"),
            "equipment_category": _first(
                record,
                "procurement_group_desc",
                "procurement_group",
                "procurement_category",
                "sector",
                "category",
            ),
            "product_family": _first(
                record,
                "procurement_method_name",
                "procurement_method",
                "procurement_type",
                "contract_type",
                "commodity",
            ),
            "estimated_value": _first(record, "estimated_value", "estimated_amount", "contract_value"),
            "currency": _first(record, "currency", "currency_code"),
            "project_reference": _first(record, "project_id", "project_reference", "project_number"),
            "procurement_stage": _first(record, "notice_type", "procurement_stage", "stage"),
            "procurement_priority": "",
        }
    return list(normalized.values())
