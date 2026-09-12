"""Retrieve bounded procurement attachments and preserve extracted text evidence."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import sqlite3
from typing import Iterable

from .evidence import decode_document_urls, extract_document_text, is_valid_document_url
from .http_client import build_session


FIELDS = [
    "procurement_document_evidence_id", "procurement_process_id",
    "procurement_release_id", "procurement_event_id", "source", "document_url",
    "fetched_at", "content_type", "byte_length", "content_hash",
    "extraction_status", "text_length", "document_text",
]


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _evidence_id(release_id: str, url: str) -> str:
    digest = sha256(f"{release_id}|{url}".encode("utf-8")).hexdigest()[:20]
    return f"proc_doc_evidence_{digest}"


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def collect_document_evidence(
    events: Iterable[dict[str, object]],
    *,
    existing_rows: Iterable[dict[str, str]] = (),
    max_documents: int = 40,
    max_bytes: int = 15_000_000,
    max_text_chars: int = 50_000,
    timeout: int = 45,
    session=None,
    fetched_at: str | None = None,
) -> list[dict[str, object]]:
    """Fetch new release/document pairs while retaining prior immutable evidence."""
    results: list[dict[str, object]] = [
        dict(row) for row in existing_rows
        if is_valid_document_url(row.get("document_url"))
    ]
    known = {
        (_text(row.get("procurement_release_id")), _text(row.get("document_url")))
        for row in results
    }
    client = session or build_session()
    fetched_at = fetched_at or _now()
    fetched = 0

    for event in events:
        release_id = _text(event.get("procurement_release_id"))
        for url in decode_document_urls(event.get("document_urls")):
            key = (release_id, url)
            if key in known:
                continue
            if fetched >= max_documents:
                break
            fetched += 1
            content_type = content_hash = document_text = ""
            byte_length = text_length = 0
            status = "FETCH_FAILED"
            try:
                response = client.get(url, timeout=timeout)
                response.raise_for_status()
                payload = response.content
                content_type = _text(response.headers.get("Content-Type"))
                byte_length = len(payload)
                content_hash = sha256(payload).hexdigest()
                if byte_length > max_bytes:
                    status = "TOO_LARGE"
                else:
                    document_text, status = extract_document_text(
                        payload,
                        content_type=content_type,
                        source_url=url,
                    )
                    document_text = document_text[:max_text_chars]
                    text_length = len(document_text)
            except Exception:
                pass
            results.append({
                "procurement_document_evidence_id": _evidence_id(release_id, url),
                "procurement_process_id": _text(event.get("procurement_process_id")),
                "procurement_release_id": release_id,
                "procurement_event_id": _text(event.get("procurement_event_id")),
                "source": _text(event.get("source")),
                "document_url": url,
                "fetched_at": fetched_at,
                "content_type": content_type,
                "byte_length": byte_length,
                "content_hash": content_hash,
                "extraction_status": status,
                "text_length": text_length,
                "document_text": document_text,
            })
            known.add(key)
    return sorted(
        results,
        key=lambda row: (
            _text(row.get("procurement_process_id")),
            _text(row.get("procurement_release_id")),
            _text(row.get("document_url")),
        ),
    )


def write_rows(path: Path, rows: Iterable[dict[str, object]]) -> int:
    output = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(output)
    return len(output)


def persist_rows(database: Path, rows: Iterable[dict[str, object]]) -> int:
    output = list(rows)
    conn = sqlite3.connect(database)
    try:
        columns = ", ".join(f'"{field}" TEXT' for field in FIELDS)
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS procurement_document_evidence ({columns}, "
            "PRIMARY KEY (procurement_document_evidence_id))"
        )
        conn.execute("DELETE FROM procurement_document_evidence")
        if output:
            placeholders = ", ".join("?" for _ in FIELDS)
            conn.executemany(
                f"INSERT INTO procurement_document_evidence ({', '.join(FIELDS)}) "
                f"VALUES ({placeholders})",
                [tuple(str(row.get(field) or "") for field in FIELDS) for row in output],
            )
        conn.commit()
    finally:
        conn.close()
    return len(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract bounded procurement document evidence.")
    parser.add_argument("--events", default="data/procurement_events.csv")
    parser.add_argument("--output", default="data/procurement_document_evidence.csv")
    parser.add_argument("--database", default="data/iati_intelligence.db")
    parser.add_argument("--max-documents", type=int, default=40)
    args = parser.parse_args()
    events = read_rows(Path(args.events))
    existing = read_rows(Path(args.output))
    rows = collect_document_evidence(
        events,
        existing_rows=existing,
        max_documents=args.max_documents,
    )
    count = write_rows(Path(args.output), rows)
    persist_rows(Path(args.database), rows)
    extracted = sum(row.get("extraction_status") == "EXTRACTED" for row in rows)
    print(f"Procurement document evidence updated: {count} documents, {extracted} extracted")


if __name__ == "__main__":
    main()
