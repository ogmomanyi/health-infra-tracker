"""Append-only procurement process and release ledger.

The shape is deliberately OCDS-inspired without claiming full OCDS conformance:
stable process identifiers group amendments, while immutable release identifiers
retain each materially different notice observation.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import sqlite3
from typing import Iterable

from .evidence import decode_document_urls, enrich_evidence_identity, is_valid_document_url
from .ingest import read_events
from .schema import ProcurementEvent


PROCESS_FIELDS = [
    "procurement_process_id", "source", "source_record_id", "tender_reference",
    "title", "buyer", "country", "source_url", "first_seen_at", "last_seen_at",
    "current_release_id", "current_content_hash", "release_count",
    "procurement_stage", "opportunity_status",
]

RELEASE_FIELDS = [
    "procurement_release_id", "procurement_process_id", "procurement_event_id",
    "content_hash", "observed_at", "source_updated_at", "source", "source_record_id",
    "tender_reference", "title", "buyer", "country", "publication_date",
    "closing_date", "project_reference", "procurement_stage", "opportunity_status",
    "source_url", "notice_text", "language", "document_urls", "is_current",
]

DOCUMENT_FIELDS = [
    "procurement_document_id", "procurement_process_id", "procurement_release_id",
    "procurement_event_id", "source", "document_url", "discovered_at", "is_current",
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _document_id(process_id: str, url: str) -> str:
    digest = sha256(f"{process_id}|{url}".encode("utf-8")).hexdigest()[:20]
    return f"proc_document_{digest}"


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS procurement_processes (
        procurement_process_id TEXT PRIMARY KEY, source TEXT, source_record_id TEXT,
        tender_reference TEXT, title TEXT, buyer TEXT, country TEXT, source_url TEXT,
        first_seen_at TEXT, last_seen_at TEXT, current_release_id TEXT,
        current_content_hash TEXT, release_count INTEGER, procurement_stage TEXT,
        opportunity_status TEXT)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS procurement_releases (
        procurement_release_id TEXT PRIMARY KEY, procurement_process_id TEXT,
        procurement_event_id TEXT, content_hash TEXT, observed_at TEXT,
        source_updated_at TEXT, source TEXT, source_record_id TEXT,
        tender_reference TEXT, title TEXT, buyer TEXT, country TEXT,
        publication_date TEXT, closing_date TEXT, project_reference TEXT,
        procurement_stage TEXT, opportunity_status TEXT, source_url TEXT,
        notice_text TEXT, language TEXT, document_urls TEXT, is_current INTEGER)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS procurement_documents (
        procurement_document_id TEXT, procurement_process_id TEXT,
        procurement_release_id TEXT, procurement_event_id TEXT, source TEXT,
        document_url TEXT, discovered_at TEXT, is_current INTEGER,
        PRIMARY KEY (procurement_release_id, document_url))"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_procurement_releases_process "
        "ON procurement_releases(procurement_process_id)"
    )


def update_notice_ledger(
    database: Path,
    events: Iterable[ProcurementEvent | dict[str, object]],
    *,
    observed_at: str | None = None,
) -> tuple[int, int, int]:
    observed_at = observed_at or _now()
    process_count = release_count = document_count = 0
    conn = sqlite3.connect(database)
    try:
        _ensure_schema(conn)
        invalid_document_urls = [
            row[0]
            for row in conn.execute("SELECT DISTINCT document_url FROM procurement_documents")
            if not is_valid_document_url(row[0])
        ]
        conn.executemany(
            "DELETE FROM procurement_documents WHERE document_url = ?",
            [(url,) for url in invalid_document_urls],
        )
        for item in events:
            raw = item.to_dict() if isinstance(item, ProcurementEvent) else dict(item)
            row = enrich_evidence_identity(raw)
            process_id = str(row["procurement_process_id"])
            release_id = str(row["procurement_release_id"])
            content_hash = str(row["content_hash"])
            existing = conn.execute(
                "SELECT first_seen_at, current_release_id FROM procurement_processes "
                "WHERE procurement_process_id = ?",
                (process_id,),
            ).fetchone()
            first_seen = existing[0] if existing else observed_at
            release_exists = conn.execute(
                "SELECT 1 FROM procurement_releases WHERE procurement_release_id = ?",
                (release_id,),
            ).fetchone()

            if not release_exists:
                conn.execute(
                    "UPDATE procurement_releases SET is_current = 0 "
                    "WHERE procurement_process_id = ?",
                    (process_id,),
                )
                conn.execute(
                    "UPDATE procurement_documents SET is_current = 0 "
                    "WHERE procurement_process_id = ?",
                    (process_id,),
                )
                release_values = {
                    **{field: str(row.get(field) or "") for field in RELEASE_FIELDS},
                    "observed_at": observed_at,
                    "is_current": 1,
                }
                conn.execute(
                    f"INSERT INTO procurement_releases ({', '.join(RELEASE_FIELDS)}) "
                    f"VALUES ({', '.join('?' for _ in RELEASE_FIELDS)})",
                    tuple(release_values[field] for field in RELEASE_FIELDS),
                )
                release_count += 1

                for url in decode_document_urls(row.get("document_urls")):
                    conn.execute(
                        "INSERT OR IGNORE INTO procurement_documents VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            _document_id(process_id, url), process_id, release_id,
                            str(row.get("procurement_event_id") or ""),
                            str(row.get("source") or ""), url, observed_at, 1,
                        ),
                    )
                    document_count += 1
            else:
                conn.execute(
                    "UPDATE procurement_releases SET is_current = "
                    "CASE WHEN procurement_release_id = ? THEN 1 ELSE 0 END "
                    "WHERE procurement_process_id = ?",
                    (release_id, process_id),
                )
                conn.execute(
                    "UPDATE procurement_documents SET is_current = "
                    "CASE WHEN procurement_release_id = ? THEN 1 ELSE 0 END "
                    "WHERE procurement_process_id = ?",
                    (release_id, process_id),
                )

            total_releases = conn.execute(
                "SELECT COUNT(*) FROM procurement_releases WHERE procurement_process_id = ?",
                (process_id,),
            ).fetchone()[0]
            process_values = {
                **{field: str(row.get(field) or "") for field in PROCESS_FIELDS},
                "first_seen_at": first_seen,
                "last_seen_at": observed_at,
                "current_release_id": release_id,
                "current_content_hash": content_hash,
                "release_count": total_releases,
            }
            conn.execute(
                f"INSERT INTO procurement_processes ({', '.join(PROCESS_FIELDS)}) "
                f"VALUES ({', '.join('?' for _ in PROCESS_FIELDS)}) "
                "ON CONFLICT(procurement_process_id) DO UPDATE SET "
                + ", ".join(
                    f"{field}=excluded.{field}"
                    for field in PROCESS_FIELDS
                    if field not in {"procurement_process_id", "first_seen_at"}
                ),
                tuple(process_values[field] for field in PROCESS_FIELDS),
            )
            process_count += 1
        conn.commit()
    finally:
        conn.close()
    return process_count, release_count, document_count


def _export_table(database: Path, table: str, fields: list[str], output: Path) -> int:
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"SELECT {', '.join(fields)} FROM {table} ORDER BY {fields[0]}"
        ).fetchall()
    finally:
        conn.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(dict(row) for row in rows)
    return len(rows)


def export_notice_ledger(database: Path, data_dir: Path) -> dict[str, int]:
    return {
        "processes": _export_table(
            database, "procurement_processes", PROCESS_FIELDS,
            data_dir / "procurement_processes.csv",
        ),
        "releases": _export_table(
            database, "procurement_releases", RELEASE_FIELDS,
            data_dir / "procurement_releases.csv",
        ),
        "documents": _export_table(
            database, "procurement_documents", DOCUMENT_FIELDS,
            data_dir / "procurement_documents.csv",
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Maintain the procurement notice release ledger.")
    parser.add_argument("--events", default="data/procurement_events.csv")
    parser.add_argument("--database", default="data/iati_intelligence.db")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    events = list(read_events(Path(args.events)))
    processes, releases, documents = update_notice_ledger(Path(args.database), events)
    totals = export_notice_ledger(Path(args.database), Path(args.data_dir))
    print(
        "Procurement ledger updated: "
        f"{processes} processes observed, {releases} new releases, "
        f"{documents} new document links; {totals['releases']} releases retained"
    )


if __name__ == "__main__":
    main()
