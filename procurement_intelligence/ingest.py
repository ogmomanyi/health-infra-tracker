import csv
import hashlib
from pathlib import Path

from .evidence import enrich_evidence_identity
from .schema import ProcurementEvent

FIELDS = [
    "procurement_event_id", "source", "source_url", "tender_reference", "title",
    "buyer", "country", "publication_date", "closing_date", "equipment_category",
    "product_family", "estimated_value", "currency", "matched_iati_identifier",
    "match_confidence", "match_status", "project_reference", "procurement_stage",
    "procurement_priority", "opportunity_status", "faram_relevance_score",
    "faram_relevance_reason", "supplier_name", "supplier_country", "award_value",
    "award_currency", "supplier_evidence_status", "supplier_entity_id",
    "supplier_canonical_name", "supplier_match_status", "supplier_match_confidence",
    "manufacturer_name", "brand_name", "manufacturer_evidence_status",
    "procurement_process_id", "procurement_release_id", "source_record_id",
    "source_updated_at", "notice_text", "language", "document_urls",
    "content_hash", "detail_fetch_status",
]


def stable_event_id(source, reference, title):
    key = "|".join((source or "", reference or "", title or "")).strip().lower()
    return "proc_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def read_events(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            row["procurement_event_id"] = row.get("procurement_event_id") or stable_event_id(row.get("source"), row.get("tender_reference"), row.get("title"))
            row = enrich_evidence_identity(row)
            yield ProcurementEvent(**{field: row.get(field, "") for field in FIELDS})


def write_events(path, events):
    rows = []
    for event in events:
        row = event.to_dict() if isinstance(event, ProcurementEvent) else dict(event)
        row["procurement_event_id"] = row.get("procurement_event_id") or stable_event_id(
            row.get("source"), row.get("tender_reference"), row.get("title")
        )
        enriched = enrich_evidence_identity(row)
        rows.append({field: enriched.get(field, "") for field in FIELDS})
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
