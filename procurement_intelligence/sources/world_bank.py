"""World Bank Procurement API adapter."""

from __future__ import annotations

from datetime import datetime
from html import unescape
import re
from typing import Any

import requests

from ..ingest import stable_event_id

DEFAULT_URL = "https://search.worldbank.org/api/v2/procnotices"

CATEGORY_RULES = (
    ("Laboratory Equipment", ("laboratory", "lab equipment", "analyzer", "analys", "centrifuge", "microscope", "spectrophotometer", "chemistry analyzer", "hematology", "haematology")),
    ("Diagnostics", ("diagnostic", "diagnostics", "test kit", "reagent", "rapid test", "molecular", "pcr", "genexpert", "gene xpert")),
    ("Medical Equipment", ("medical equipment", "medical device", "patient monitor", "ventilator", "ultrasound", "x-ray", "radiology", "operating theatre", "surgical equipment")),
    ("Blood Banking", ("blood bank", "blood banking", "blood storage", "blood refrigerator", "blood component", "apheresis")),
    ("Cold Chain", ("cold chain", "vaccine refrigerator", "vaccine carrier", "freezer", "refrigerator")),
    ("Sterilization", ("sterilizer", "sterilisation", "sterilization", "autoclave", "disinfection", "decontamination")),
    ("PPE", ("personal protective", "ppe", "surgical glove", "examination glove", "face mask", "respirator", "protective gown")),
    ("Ophthalmology", ("ophthalm", "ophthalmic", "optical", "slit lamp", "tonometer", "fundus")),
    ("Laboratory Consumables", ("laboratory consumable", "lab consumable", "consumables", "disposable", "pipette tip", "tube", "specimen collection")),
)


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
    params: dict[str, Any] = {"format": "json", "rows": rows, "os": 0}
    if country_codes:
        country_names = {"KE": "Kenya", "UG": "Uganda", "RW": "Rwanda", "ET": "Ethiopia", "SO": "Somalia", "SS": "South Sudan", "CD": "Congo, Democratic Republic of the"}
        params["project_ctry_name"] = ";".join(country_names.get(code.upper(), code) for code in country_codes)
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return _records(response.json())


def _normalise_date(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if "T" in value and value.endswith("Z"):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            pass
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return value


def _plain_text(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _deadline_from_notice_text(record: dict[str, Any]) -> str:
    text = _plain_text(_first(record, "notice_text"))
    if not text:
        return ""
    patterns = (r"(?:submission|bid|proposal|application)\s+deadline\s*[:\-]?\s*([A-Za-z0-9, /-]{8,40})", r"deadline\s+(?:for\s+submission|for\s+submitting)\s*[:\-]?\s*([A-Za-z0-9, /-]{8,40})")
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            candidate = match.group(1).strip(" .;,")
            for fmt in ("%B %d, %Y", "%b %d, %Y", "%d-%b-%Y", "%d %B %Y", "%d %b %Y"):
                try:
                    return datetime.strptime(candidate, fmt).date().isoformat()
                except ValueError:
                    continue
    return ""


def _extract_award_evidence(record: dict[str, Any], notice_text: str, stage: str) -> tuple[str, str, str, str, str]:
    """Return supplier, supplier country, value, currency and evidence status.

    Supplier attribution is deliberately limited to explicit award fields or
    recognisable award-language in the notice text. No incumbent is inferred.
    """
    combined = " ".join((_first(record, "notice_type", "procurement_stage", "stage"), notice_text)).strip()
    award_stage = bool(re.search(r"contract\s+award|award\s+notice|award(ed)?\s+(bidder|contract|supplier|firm)|recommended\s+(bidder|supplier|firm)", combined, re.I)) or stage.strip().lower() == "award"
    if not award_stage:
        return "", "", "", "", "NONE"

    supplier = _first(record, "awarded_bidder_name", "awarded_supplier_name", "awarded_firm", "awardee_name", "winner_name", "recommended_bidder_name", "supplier_name", "contractor_name")
    supplier_country = _first(record, "awarded_bidder_country", "awarded_supplier_country", "supplier_country", "contractor_country", "awardee_country")
    value = _first(record, "award_value", "contract_award_value", "awarded_amount", "contract_amount", "signed_contract_price")
    currency = _first(record, "award_currency", "contract_currency", "currency", "currency_code")

    if not supplier:
        patterns = (
            r"(?:awarded|recommended)\s+(?:bidder|supplier|firm|contractor)\s*[:\-]\s*([^;\n|]+)",
            r"(?:name of (?:the )?(?:awarded|recommended) (?:bidder|supplier|firm|contractor))\s*[:\-]\s*([^;\n|]+)",
        )
        for pattern in patterns:
            match = re.search(pattern, notice_text, re.I)
            if match:
                supplier = re.sub(r"\s+", " ", match.group(1)).strip(" .")
                break
    if supplier:
        return supplier, supplier_country, value, currency, "EXPLICIT"
    return "", "", "", "", "AWARD_WITHOUT_SUPPLIER"


def classify_equipment(title: str, notice_text: str = "", procurement_group: str = "") -> str:
    text = " ".join(part for part in (title, notice_text) if part).lower()
    for category, terms in CATEGORY_RULES:
        if any(term in text for term in terms):
            return category
    return procurement_group or "Other"


def normalize_notices(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for record in records:
        reference = _first(record, "id", "notice_id")
        title = _first(record, "bid_description", "notice_title", "title", "procurement_name", "description", "contract_description")
        if not reference and not title:
            continue
        notice_text = _first(record, "notice_text", "description", "contract_description")
        procurement_group = _first(record, "procurement_group_desc", "procurement_group", "sector", "category", "procurement_category")
        stage = _first(record, "notice_type", "procurement_stage", "stage")
        supplier, supplier_country, award_value, award_currency, evidence = _extract_award_evidence(record, notice_text, stage)
        event_id = stable_event_id("World Bank", reference, title)
        normalized[event_id] = {
            "procurement_event_id": event_id,
            "source": "World Bank",
            "source_url": f"https://search.worldbank.org/api/v2/procnotices?format=json&id={reference}" if reference else "",
            "tender_reference": _first(record, "bid_reference_no", "bid_reference", "bid_no", "procurement_number", "procurement_reference"),
            "title": title,
            "buyer": _first(record, "contact_organization", "borrower_name", "borrower", "buyer", "agency", "implementing_agency", "organization"),
            "country": _first(record, "project_ctry_name", "country_name", "country", "countryname"),
            "publication_date": _normalise_date(_first(record, "noticedate", "notice_date", "publication_date", "published_date", "date_published")),
            "closing_date": _normalise_date(_first(record, "submission_deadline_date", "deadline_date", "deadline", "closing_date", "submission_deadline", "bid_deadline")) or _deadline_from_notice_text(record),
            "equipment_category": classify_equipment(title, notice_text, procurement_group),
            "product_family": _first(record, "procurement_method_name", "procurement_method", "procurement_type", "contract_type", "commodity"),
            "estimated_value": _first(record, "estimated_value", "estimated_amount", "contract_value"),
            "currency": _first(record, "currency", "currency_code"),
            "project_reference": _first(record, "project_id", "project_reference", "project_number"),
            "procurement_stage": stage,
            "procurement_priority": "",
            "supplier_name": supplier,
            "supplier_country": supplier_country,
            "award_value": award_value,
            "award_currency": award_currency,
            "supplier_evidence_status": evidence,
        }
    return list(normalized.values())
