"""Load and validate Faram's controlled product specification registry.

Technical specifications are separate from product identity so that a product
can be maintained independently from its changing specification evidence.
Only explicitly verified records should be consumed by downstream matching.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

REQUIRED_FIELDS = (
    "faram_product_id",
    "specification_name",
    "specification_value",
    "specification_unit",
    "source",
    "source_reference",
    "verification_status",
)
VALID_VERIFICATION_STATUSES = {"VERIFIED", "UNVERIFIED", "EXPIRED", "DISPUTED"}
MATCHABLE_VERIFICATION_STATUS = "VERIFIED"


@dataclass(frozen=True)
class SpecificationIssue:
    row_number: int
    field: str
    message: str


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _norm(value: object) -> str:
    return _text(value).casefold()


def load_specifications(path: Path) -> list[dict[str, str]]:
    """Load the controlled specification registry; a missing file is empty."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def validate_specifications(rows: list[dict[str, str]]) -> list[SpecificationIssue]:
    """Validate specification identity, provenance and verification state."""
    issues: list[SpecificationIssue] = []
    seen: dict[tuple[str, str, str], int] = {}

    for row_number, row in enumerate(rows, start=2):
        for field in REQUIRED_FIELDS:
            if not _text(row.get(field)):
                issues.append(SpecificationIssue(row_number, field, "required value is blank"))

        status = _norm(row.get("verification_status"))
        if status and status.upper() not in VALID_VERIFICATION_STATUSES:
            issues.append(
                SpecificationIssue(
                    row_number,
                    "verification_status",
                    f"unsupported status: {row.get('verification_status')}",
                )
            )

        key = (
            _norm(row.get("faram_product_id")),
            _norm(row.get("specification_name")),
            _norm(row.get("specification_unit")),
        )
        if all(key):
            if key in seen:
                issues.append(
                    SpecificationIssue(
                        row_number,
                        "specification_name",
                        f"duplicate specification of row {seen[key]}",
                    )
                )
            else:
                seen[key] = row_number

    return issues


def specifications_by_product(
    rows: list[dict[str, str]], *, verified_only: bool = True
) -> dict[str, list[dict[str, str]]]:
    """Group specifications by product, optionally excluding unverified evidence."""
    result: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        product_id = _text(row.get("faram_product_id"))
        if not product_id:
            continue
        if verified_only and _norm(row.get("verification_status")).upper() != MATCHABLE_VERIFICATION_STATUS:
            continue
        result.setdefault(product_id, []).append(dict(row))
    return result
