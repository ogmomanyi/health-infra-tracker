"""World Bank Procurement API adapter."""

from __future__ import annotations

from datetime import datetime
from html import unescape
import re
from typing import Any

from bs4 import BeautifulSoup

from ..evidence import discover_document_links, encode_document_urls
from ..http_client import build_session
from ..ingest import stable_event_id
from ..manufacturer_extraction import extract_explicit_manufacturer_brand

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
HEALTH_CATEGORIES = {category for category, _ in CATEGORY_RULES}


def _first(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list): return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict): return []
    for key in ("procnotices", "procurement", "notices", "results", "documents"):
        value = payload.get(key)
        if isinstance(value, list): return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            nested = value.get("records") or value.get("results") or value.get("documents")
            if isinstance(nested, list): return [x for x in nested if isinstance(x, dict)]
    return []


def fetch_notices(
    *,
    url: str = DEFAULT_URL,
    country_codes: list[str] | None = None,
    rows: int = 500,
    max_pages: int = 20,
    timeout: int = 30,
    session=None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"format": "json", "rows": rows, "os": 0}
    if country_codes:
        country_names = {"KE": "Kenya", "UG": "Uganda", "RW": "Rwanda", "ET": "Ethiopia", "SO": "Somalia", "SS": "South Sudan", "CD": "Congo, Democratic Republic of the"}
        params["project_ctry_name"] = ";".join(country_names.get(code.upper(), code) for code in country_codes)
    client = session or build_session()
    collected: list[dict[str, Any]] = []
    for page in range(max_pages):
        params["os"] = page * rows
        response = client.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        records = _records(response.json())
        collected.extend(records)
        if len(records) < rows:
            break
    return collected


def _normalise_date(value: str) -> str:
    value = (value or "").strip()
    if not value: return ""
    if "T" in value and value.endswith("Z"):
        try: return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        except ValueError: pass
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d"):
        try: return datetime.strptime(value, fmt).date().isoformat()
        except ValueError: continue
    return value


def _plain_text(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", unescape(text)).strip()


def is_health_procurement(record: dict[str, Any]) -> bool:
    """Return true for notices classified into the platform's health taxonomy."""
    return str(record.get("equipment_category") or "") in HEALTH_CATEGORIES


def _html_award_evidence(raw_html: str) -> tuple[str, str, str, str]:
    """Extract the first awarded party and signed price from World Bank HTML."""
    if not raw_html or "<" not in raw_html:
        return "", "", "", ""
    soup = BeautifulSoup(raw_html, "html.parser")
    heading = soup.find(string=re.compile(r"Awarded\s+(?:Firm|Bidder|Supplier)\(s\)", re.I))
    supplier = supplier_country = ""
    if heading:
        for node in heading.parent.find_all_next(["b", "strong"]):
            value = _plain_text(node.get_text(" ", strip=True))
            if re.search(r"^(?:Evaluated|Rejected)\s+(?:Firm|Bidder|Supplier)", value, re.I):
                break
            if re.search(r"^Awarded\s+(?:Firm|Bidder|Supplier)", value, re.I):
                continue
            if not value or value.endswith(":") or value.casefold() in {
                "beneficial ownership details", "scores", "final evaluation price",
                "signed contract price", "price",
            }:
                continue
            supplier = re.sub(r"\s*\(\d+\)\s*$", "", value).strip()
            context = node.parent.get_text(" ", strip=True)
            country_match = re.search(r"\bCountry\s*:\s*([^;|]+?)(?:\s{2,}|$)", context, re.I)
            if country_match:
                supplier_country = country_match.group(1).strip()
            break

    plain = soup.get_text(" ", strip=True)
    price_match = re.search(
        r"Signed\s+Contract\s+[Pp]rice\s+([A-Z]{3})\s+([\d,.]+)",
        plain,
    )
    if not price_match:
        price_match = re.search(
            r"Signed\s+Contract\s+[Pp]rice\s+([\d,.]+)\s+([A-Z]{3})",
            plain,
        )
        if price_match:
            return supplier, supplier_country, price_match.group(1).replace(",", ""), price_match.group(2)
    if price_match:
        return supplier, supplier_country, price_match.group(2).replace(",", ""), price_match.group(1)
    return supplier, supplier_country, "", ""


def _deadline_from_notice_text(record: dict[str, Any]) -> str:
    text = _plain_text(_first(record, "notice_text"))
    if not text: return ""
    patterns = (r"(?:submission|bid|proposal|application)\s+deadline\s*[:\-]?\s*([A-Za-z0-9, /-]{8,40})", r"deadline\s+(?:for\s+submission|for\s+submitting)\s*[:\-]?\s*([A-Za-z0-9, /-]{8,40})")
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            candidate = match.group(1).strip(" .;,")
            for fmt in ("%B %d, %Y", "%b %d, %Y", "%d-%b-%Y", "%d %B %Y", "%d %b %Y"):
                try: return datetime.strptime(candidate, fmt).date().isoformat()
                except ValueError: continue
    return ""


def _extract_award_evidence(record: dict[str, Any], notice_text: str, stage: str) -> tuple[str, str, str, str, str]:
    combined = " ".join((_first(record, "notice_type", "procurement_stage", "stage"), notice_text)).strip()
    award_stage = bool(re.search(r"contract\s+award|award\s+notice|award(ed)?\s+(bidder|contract|supplier|firm)|recommended\s+(bidder|supplier|firm)", combined, re.I)) or stage.strip().lower() == "award"
    if not award_stage: return "", "", "", "", "NONE"
    supplier = _first(record, "awarded_bidder_name", "awarded_supplier_name", "awarded_firm", "awardee_name", "winner_name", "recommended_bidder_name", "supplier_name", "contractor_name")
    supplier_country = _first(record, "awarded_bidder_country", "awarded_supplier_country", "supplier_country", "contractor_country", "awardee_country")
    value = _first(record, "award_value", "contract_award_value", "awarded_amount", "contract_amount", "signed_contract_price")
    currency = _first(record, "award_currency", "contract_currency", "currency", "currency_code")
    html_supplier, html_country, html_value, html_currency = _html_award_evidence(
        _first(record, "notice_text")
    )
    supplier = supplier or html_supplier
    supplier_country = supplier_country or html_country
    value = value or html_value
    currency = currency or html_currency
    if not supplier:
        for pattern in (r"(?:awarded|recommended)\s+(?:bidder|supplier|firm|contractor)\s*[:\-]\s*([^;\n|]+)", r"(?:name of (?:the )?(?:awarded|recommended) (?:bidder|supplier|firm|contractor))\s*[:\-]\s*([^;\n|]+)"):
            match = re.search(pattern, notice_text, re.I)
            if match:
                supplier = re.sub(r"\s+", " ", match.group(1)).strip(" ."); break
    if supplier: return supplier, supplier_country, value, currency, "EXPLICIT"
    return "", "", "", "", "AWARD_WITHOUT_SUPPLIER"


def classify_equipment(title: str, notice_text: str = "", procurement_group: str = "") -> str:
    text = " ".join(part for part in (title, notice_text) if part).lower()
    for category, terms in CATEGORY_RULES:
        if any(term in text for term in terms): return category
    return procurement_group or "Other"


def normalize_notices(
    records: list[dict[str, Any]],
    *,
    health_only: bool = False,
) -> list[dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for record in records:
        reference = _first(record, "id", "notice_id")
        title = _first(record, "bid_description", "notice_title", "title", "procurement_name", "description", "contract_description")
        if not reference and not title: continue
        raw_notice_text = _first(record, "notice_text", "description", "contract_description")
        notice_text = _plain_text(raw_notice_text)[:12000]
        procurement_group = _first(record, "procurement_group_desc", "procurement_group", "sector", "category", "procurement_category")
        equipment_category = classify_equipment(title, notice_text, procurement_group)
        if health_only and equipment_category not in HEALTH_CATEGORIES:
            continue
        stage = _first(record, "notice_type", "procurement_stage", "stage")
        supplier, supplier_country, award_value, award_currency, evidence = _extract_award_evidence(record, notice_text, stage)
        manufacturer, brand, manufacturer_evidence = extract_explicit_manufacturer_brand(record, notice_text)
        event_id = stable_event_id("World Bank", reference, title)
        source_url = _first(record, "notice_url", "source_url", "url") or (
            f"https://search.worldbank.org/api/v2/procnotices?format=json&id={reference}"
            if reference else ""
        )
        explicit_documents = [
            _first(record, key)
            for key in (
                "document_url", "attachment_url", "bid_document_url",
                "procurement_document_url", "notice_pdf_url",
            )
        ]
        document_urls = [url for url in explicit_documents if url]
        document_urls.extend(discover_document_links(raw_notice_text, source_url))
        normalized[event_id] = {
            "procurement_event_id": event_id, "source": "World Bank",
            "source_url": source_url,
            "tender_reference": _first(record, "bid_reference_no", "bid_reference", "bid_no", "procurement_number", "procurement_reference"),
            "title": title, "buyer": _first(record, "contact_organization", "borrower_name", "borrower", "buyer", "agency", "implementing_agency", "organization"),
            "country": _first(record, "project_ctry_name", "country_name", "country", "countryname"),
            "publication_date": _normalise_date(_first(record, "noticedate", "notice_date", "publication_date", "published_date", "date_published")),
            "closing_date": _normalise_date(_first(record, "submission_deadline_date", "deadline_date", "deadline", "closing_date", "submission_deadline", "bid_deadline")) or _deadline_from_notice_text(record),
            "equipment_category": equipment_category,
            "product_family": _first(record, "procurement_method_name", "procurement_method", "procurement_type", "contract_type", "commodity"),
            "estimated_value": _first(record, "estimated_value", "estimated_amount", "contract_value"), "currency": _first(record, "currency", "currency_code"),
            "project_reference": _first(record, "project_id", "project_reference", "project_number"), "procurement_stage": stage,
            "procurement_priority": "", "supplier_name": supplier, "supplier_country": supplier_country,
            "award_value": award_value, "award_currency": award_currency, "supplier_evidence_status": evidence,
            "manufacturer_name": manufacturer, "brand_name": brand, "manufacturer_evidence_status": manufacturer_evidence,
            "source_record_id": reference,
            "source_updated_at": _normalise_date(_first(record, "last_updated_date", "updated_date", "modified_date")),
            "notice_text": notice_text,
            "language": _first(record, "language", "lang", "notice_language", "notice_lang_name"),
            "document_urls": encode_document_urls(document_urls),
            "detail_fetch_status": "EMBEDDED" if notice_text else "NOT_AVAILABLE",
        }
    return list(normalized.values())
