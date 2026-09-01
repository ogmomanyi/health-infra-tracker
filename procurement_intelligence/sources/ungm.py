"""UNGM procurement-event normalization.

This adapter intentionally accepts already-extracted notice dictionaries. It keeps
source retrieval separate from normalization so public scraping, an authenticated
UNGM API client, or fixture data can all feed the same pipeline.
"""

from ..schema import ProcurementEvent
from ..ingest import stable_event_id


def _first(record, *keys):
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def normalize_notice(record):
    source = "UNGM"
    reference = _first(record, "tender_reference", "reference", "notice_reference", "id")
    title = _first(record, "title", "notice_title", "description")
    event_id = _first(record, "procurement_event_id") or stable_event_id(source, reference, title)

    estimated_value = record.get("estimated_value", record.get("value", ""))
    if estimated_value in (None, ""):
        estimated_value = None
    else:
        try:
            estimated_value = float(str(estimated_value).replace(",", "").strip())
        except (TypeError, ValueError):
            estimated_value = None

    return ProcurementEvent(
        procurement_event_id=event_id,
        source=source,
        source_url=_first(record, "source_url", "url", "notice_url"),
        tender_reference=reference,
        title=title,
        buyer=_first(record, "buyer", "agency", "organization", "organisation"),
        country=_first(record, "country", "country_name"),
        publication_date=_first(record, "publication_date", "published", "date_published"),
        closing_date=_first(record, "closing_date", "deadline", "date_closing"),
        equipment_category=_first(record, "equipment_category", "category"),
        product_family=_first(record, "product_family", "product", "commodity"),
        estimated_value=estimated_value,
        currency=_first(record, "currency", "currency_code"),
        matched_iati_identifier=_first(record, "matched_iati_identifier"),
        match_confidence=float(record.get("match_confidence") or 0.0),
        match_status=_first(record, "match_status") or "UNMATCHED",
    )


def normalize_notices(records):
    """Normalize notices and deduplicate by stable procurement event ID."""
    events = {}
    for record in records:
        event = normalize_notice(record)
        events[event.procurement_event_id] = event
    return list(events.values())
