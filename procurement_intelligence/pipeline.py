"""Persistence and integration helpers for normalized procurement events."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .ingest import FIELDS, read_events, write_events
from .schema import ProcurementEvent


def load_events(path: str | Path) -> list[ProcurementEvent]:
    path = Path(path)
    if not path.exists():
        return []
    return list(read_events(path))


def deduplicate_events(events):
    unique = {}
    for event in events:
        unique[event.procurement_event_id] = event
    return list(unique.values())


def merge_events(existing, fresh):
    """Merge a newly collected source snapshot into retained event history.

    Fresh records win on duplicate event IDs so corrected fields and latest
    IATI matching are retained, while historical records that are no longer
    present in a source listing are preserved for dashboard/history use.
    """
    merged = {}
    for event in existing:
        merged[event.procurement_event_id] = event
    for event in fresh:
        merged[event.procurement_event_id] = event
    return list(merged.values())


def persist_events(db_path: str | Path, events, table_name: str = "procurement_intelligence"):
    events = deduplicate_events(events)
    columns = ", ".join(f'"{field}" TEXT' for field in FIELDS)
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(f'CREATE TABLE IF NOT EXISTS "{table_name}" ({columns})')
        conn.execute(f'DELETE FROM "{table_name}"')
        placeholders = ", ".join("?" for _ in FIELDS)
        rows = [tuple(event.to_dict().get(field, "") for field in FIELDS) for event in events]
        if rows:
            conn.executemany(f'INSERT INTO "{table_name}" ({", ".join(FIELDS)}) VALUES ({placeholders})', rows)
        conn.commit()
    finally:
        conn.close()
    return len(events)


def sync_events(data_dir: str | Path, db_path: str | Path, input_name: str = "procurement_events.csv") -> int:
    data_dir = Path(data_dir)
    events = deduplicate_events(load_events(data_dir / input_name))
    write_events(data_dir / "procurement_events.csv", events)
    return persist_events(db_path, events)
