import csv
import hashlib
from pathlib import Path

from .schema import ProcurementEvent

FIELDS = [
    "procurement_event_id", "source", "source_url", "tender_reference", "title",
    "buyer", "country", "publication_date", "closing_date", "equipment_category",
    "product_family", "estimated_value", "currency", "matched_iati_identifier",
    "match_confidence", "match_status",
]


def stable_event_id(source, reference, title):
    key = "|".join((source or "", reference or "", title or "")).strip().lower()
    return "proc_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def read_events(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            row["procurement_event_id"] = row.get("procurement_event_id") or stable_event_id(row.get("source"), row.get("tender_reference"), row.get("title"))
            yield ProcurementEvent(**{field: row.get(field, "") for field in FIELDS})


def write_events(path, events):
    rows = [event.to_dict() if isinstance(event, ProcurementEvent) else event for event in events]
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
