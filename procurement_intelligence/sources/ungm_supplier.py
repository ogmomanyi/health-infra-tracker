"""Supplier-controlled UNGM ingestion.

UNGM has confirmed that API access is restricted to UN staff. This adapter
therefore accepts data that the supplier is authorized to obtain, such as a
UNGM Pro alert export or a locally prepared CSV/JSON notice feed. It performs
no login, scraping, API calls, or credential handling.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable


def _records_from_json(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        return (item for item in payload if isinstance(item, dict))

    if isinstance(payload, dict):
        for key in ("notices", "items", "value", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return (item for item in value if isinstance(item, dict))
        return (payload,)

    return ()


def read_supplier_records(path: str | Path) -> list[dict[str, Any]]:
    """Read supplier-controlled UNGM records from CSV or JSON."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"UNGM supplier feed not found: {path}")

    if path.suffix.lower() == ".json":
        with path.open(encoding="utf-8") as handle:
            return list(_records_from_json(json.load(handle)))

    if path.suffix.lower() != ".csv":
        raise ValueError("UNGM supplier feed must be a .csv or .json file")

    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def load_supplier_notices(path: str | Path) -> list[dict[str, Any]]:
    """Validate the minimum fields and normalize source metadata."""
    records = read_supplier_records(path)
    notices: list[dict[str, Any]] = []

    for index, record in enumerate(records, start=1):
        clean = {
            str(key): value.strip() if isinstance(value, str) else value
            for key, value in record.items()
            if key is not None
        }

        title = clean.get("title") or clean.get("notice_title") or clean.get("description")
        reference = (
            clean.get("tender_reference")
            or clean.get("reference")
            or clean.get("notice_reference")
            or clean.get("noticeId")
            or clean.get("id")
        )
        if not title and not reference:
            raise ValueError(
                f"UNGM supplier record {index} has neither title nor reference"
            )

        clean["source"] = clean.get("source") or "UNGM"
        clean["title"] = title or ""
        clean["tender_reference"] = reference or ""
        notices.append(clean)

    return notices


__all__ = ["read_supplier_records", "load_supplier_notices"]
