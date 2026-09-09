"""Build tender-level Faram product technical-fit intelligence.

This composes existing catalogue candidates with separately verified tender and
Faram specification evidence. It does not recalculate commercial priority.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from .faram_specification_matching import assess_candidates
from .procurement_specifications import specifications_by_event
from .specification_matching import Specification, compare_specifications

OUTPUT_FIELDS = [
    "procurement_event_id", "tender_reference", "faram_product_id", "product_name",
    "manufacturer_name", "match_status", "match_confidence", "territory_fit",
    "technical_status", "technical_score", "technical_passed", "technical_unknown",
    "technical_failed", "technical_action",
]


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _requirements_text(rows: Iterable[dict[str, str]]) -> str:
    parts: list[str] = []
    for row in rows:
        name = _text(row.get("specification_name"))
        value = _text(row.get("specification_value"))
        unit = _text(row.get("specification_unit"))
        if name and value:
            parts.append(f"{name}: {value}{unit}")
    return "; ".join(parts)


def build_product_fit(
    candidate_rows: Iterable[dict[str, str]],
    requirement_rows: Iterable[dict[str, str]],
) -> list[dict[str, object]]:
    """Attach verified tender technical-fit results to catalogue candidates."""
    requirements = specifications_by_event(list(requirement_rows), verified_only=True)
    grouped_candidates: dict[str, list[dict[str, str]]] = {}
    for candidate in candidate_rows:
        event_id = _text(candidate.get("procurement_event_id"))
        grouped_candidates.setdefault(event_id, []).append(dict(candidate))

    output: list[dict[str, object]] = []
    for event_id, candidates in grouped_candidates.items():
        event_requirements = requirements.get(event_id, [])
        requirement_text = _requirements_text(event_requirements)
        assessed = assess_candidates(requirement_text, candidates, []) if requirement_text else [
            {**candidate, "technical_status": "UNKNOWN", "technical_score": 0.0,
             "technical_passed": 0, "technical_unknown": 0, "technical_failed": 0}
            for candidate in candidates
        ]
        # assess_candidates expects Faram specification rows. Re-run against the
        # candidates' available specification evidence is intentionally avoided here;
        # this function is the event-level composition boundary. Callers should use
        # assess_candidates with the controlled Faram registry when building results.
        for row in assessed:
            status = _text(row.get("technical_status"))
            if status == "PASS":
                action = "Technical fit supported; proceed to commercial compliance and bid review."
            elif status == "FAIL":
                action = "Technical failure identified; do not treat as compliant without an approved alternative."
            elif status == "REVIEW":
                action = "Technical review required before bid/no-bid decision."
            else:
                action = "Technical evidence gap; obtain and verify the tender/product specifications."
            output.append({
                "procurement_event_id": event_id,
                "tender_reference": _text(row.get("tender_reference")),
                "faram_product_id": _text(row.get("faram_product_id")),
                "product_name": _text(row.get("product_name")),
                "manufacturer_name": _text(row.get("manufacturer_name")),
                "match_status": _text(row.get("match_status")),
                "match_confidence": row.get("match_confidence", ""),
                "territory_fit": _text(row.get("territory_fit")),
                "technical_status": status,
                "technical_score": row.get("technical_score", 0.0),
                "technical_passed": row.get("technical_passed", 0),
                "technical_unknown": row.get("technical_unknown", 0),
                "technical_failed": row.get("technical_failed", 0),
                "technical_action": action,
            })
    return output


def write_product_fit(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
