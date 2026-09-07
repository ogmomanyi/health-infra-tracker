"""Validate and index Faram's controlled product/principal catalogue.

External procurement evidence must never create catalogue records automatically.
This module validates the human-controlled CSV and exposes conservative
manufacturer/principal coverage for downstream intelligence.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

REQUIRED_FIELDS = (
    "faram_product_id",
    "product_name",
    "manufacturer_name",
    "product_family",
    "equipment_category",
    "principal_status",
    "territory",
)
ACTIVE_STATUSES = {"active", "approved", "current"}
VALID_STATUSES = ACTIVE_STATUSES | {"inactive", "prospect", "pending", "unknown"}


@dataclass(frozen=True)
class CatalogueIssue:
    row_number: int
    field: str
    message: str


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _norm(value: object) -> str:
    return _text(value).casefold()


def load_catalogue(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def validate_catalogue(rows: list[dict[str, str]]) -> list[CatalogueIssue]:
    issues: list[CatalogueIssue] = []
    seen_ids: dict[str, int] = {}
    seen_commercial_keys: dict[tuple[str, str, str], int] = {}

    for row_number, row in enumerate(rows, start=2):
        for field in REQUIRED_FIELDS:
            if not _text(row.get(field)):
                issues.append(CatalogueIssue(row_number, field, "required value is blank"))

        product_id = _text(row.get("faram_product_id"))
        if product_id:
            if product_id in seen_ids:
                issues.append(CatalogueIssue(row_number, "faram_product_id", f"duplicate of row {seen_ids[product_id]}"))
            else:
                seen_ids[product_id] = row_number

        status = _norm(row.get("principal_status"))
        if status and status not in VALID_STATUSES:
            issues.append(CatalogueIssue(row_number, "principal_status", f"unsupported status: {row.get('principal_status')}"))

        key = (
            _norm(row.get("manufacturer_name")),
            _norm(row.get("product_name")),
            _norm(row.get("model")),
        )
        if all(key):
            if key in seen_commercial_keys:
                issues.append(CatalogueIssue(row_number, "product_name", f"duplicate commercial record of row {seen_commercial_keys[key]}"))
            else:
                seen_commercial_keys[key] = row_number

    return issues


def manufacturer_coverage(rows: list[dict[str, str]]) -> dict[str, dict[str, object]]:
    """Summarize catalogue coverage by normalized manufacturer name."""
    result: dict[str, dict[str, object]] = {}
    for row in rows:
        manufacturer = _text(row.get("manufacturer_name"))
        key = _norm(manufacturer)
        if not key:
            continue
        entry = result.setdefault(
            key,
            {
                "manufacturer_name": manufacturer,
                "product_count": 0,
                "active_product_count": 0,
                "principal_statuses": set(),
                "products": set(),
                "territories": set(),
            },
        )
        entry["product_count"] += 1
        status = _norm(row.get("principal_status")) or "unknown"
        entry["principal_statuses"].add(status)
        product = _text(row.get("product_name"))
        if product:
            entry["products"].add(product)
        territory = _text(row.get("territory"))
        if territory:
            entry["territories"].add(territory)
        if status in ACTIVE_STATUSES:
            entry["active_product_count"] += 1
    return result


def write_validation_report(path: Path, issues: list[CatalogueIssue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("row_number", "field", "message"))
        writer.writerows((issue.row_number, issue.field, issue.message) for issue in issues)
