"""Read-only procurement evidence projection for a commercial opportunity."""

from __future__ import annotations

import csv
from pathlib import Path


DATA_DIR = Path("data")
EVENTS_DEFAULT = DATA_DIR / "procurement_events.csv"
LINE_ITEMS_DEFAULT = DATA_DIR / "procurement_line_items.csv"
RELEASES_DEFAULT = DATA_DIR / "procurement_releases.csv"
DOCUMENTS_DEFAULT = DATA_DIR / "procurement_document_evidence.csv"
RELATIONSHIPS_DEFAULT = DATA_DIR / "procurement_manufacturer_relationships.csv"


def _read(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def for_account(
    target_account_id: str,
    *,
    relationships_path: Path = RELATIONSHIPS_DEFAULT,
) -> list[dict[str, str]]:
    return [
        row for row in _read(relationships_path)
        if row.get("target_account_id") == target_account_id
    ]


def enrich_accounts(
    accounts: list[dict[str, object]],
    *,
    relationships_path: Path = RELATIONSHIPS_DEFAULT,
) -> list[dict[str, object]]:
    """Attach relationships and retain relationship-only target accounts."""
    indexed = {
        str(account.get("target_account_id") or ""): account for account in accounts
    }
    for account in indexed.values():
        account["manufacturer_relationships"] = []
    for relationship in _read(relationships_path):
        account_id = str(relationship.get("target_account_id") or "")
        if not account_id:
            continue
        account = indexed.setdefault(account_id, {
            "target_account_id": account_id,
            "account_name": relationship.get("party_name") or "Unknown account",
            "country": relationship.get("country") or "",
            "account_type": relationship.get("party_role") or "",
            "opportunities": [],
            "active_opportunities": 0,
            "outstanding_actions": 0,
            "overdue_actions": 0,
            "highest_priority_score": None,
            "highest_priority_tier": "",
            "manufacturer_relationships": [],
        })
        account["manufacturer_relationships"].append(relationship)
    return sorted(
        indexed.values(),
        key=lambda account: (
            not bool(account.get("manufacturer_relationships")),
            -int(account.get("overdue_actions") or 0),
            str(account.get("account_name") or "").casefold(),
        ),
    )


def for_event(
    event_id: str,
    *,
    events_path: Path = EVENTS_DEFAULT,
    line_items_path: Path = LINE_ITEMS_DEFAULT,
    releases_path: Path = RELEASES_DEFAULT,
    documents_path: Path = DOCUMENTS_DEFAULT,
    relationships_path: Path = RELATIONSHIPS_DEFAULT,
) -> dict[str, object]:
    event = next(
        (row for row in _read(events_path) if row.get("procurement_event_id") == event_id),
        None,
    )
    if not event:
        return {
            "event": None,
            "line_items": [],
            "releases": [],
            "documents": [],
            "manufacturer_relationships": [],
        }

    process_id = event.get("procurement_process_id") or ""
    line_items = [
        row for row in _read(line_items_path)
        if row.get("procurement_event_id") == event_id
    ]
    releases = [
        row for row in _read(releases_path)
        if row.get("procurement_process_id") == process_id
    ]
    releases.sort(key=lambda row: row.get("observed_at") or "", reverse=True)
    documents = [
        row for row in _read(documents_path)
        if row.get("procurement_process_id") == process_id
        or row.get("procurement_event_id") == event_id
    ]
    manufacturer_relationships = [
        row for row in _read(relationships_path)
        if event_id in {
            value.strip()
            for value in (row.get("procurement_event_ids") or "").split(";")
            if value.strip()
        }
    ]
    return {
        "event": event,
        "line_items": line_items,
        "releases": releases,
        "documents": documents,
        "manufacturer_relationships": manufacturer_relationships,
    }
