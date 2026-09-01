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
    """Keep one event per stable procurement-event ID, deterministically."""
    unique = {}
    for event in events:
        unique[event.procurement_event_id] = event
    return list(unique.values())


def persist_events(db_path: str | Path, events, table_name: str = "procurement_intelligence"):
    """Replace the normalized procurement table with the supplied event snapshot."""
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
            conn.executemany(
                f'INSERT INTO "{table_name}" ({", ".join(FIELDS)}) VALUES ({placeholders})',
                rows,
            )
        conn.commit()
    finally:
        conn.close()
    return len(events)


def sync_events(data_dir: str | Path, db_path: str | Path, input_name: str = "procurement_events.csv") -> int:
    """Load, deduplicate, persist, and rewrite the canonical procurement CSV."""
    data_dir = Path(data_dir)
    input_path = data_dir / input_name
    events = load_events(input_path)
    events = deduplicate_events(events)
    output_path = data_dir / "procurement_events.csv"
    write_events(output_path, events)
    return persist_events(db_path, events)
