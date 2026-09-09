"""Compose controlled Faram catalogue matching with verified specifications.

This layer deliberately keeps commercial priority scoring separate. Catalogue
fit and technical specification status are evidence about product suitability,
not a replacement for the canonical commercial account priority score.
"""

from __future__ import annotations

from typing import Iterable

from .specification_matching import Specification, compare_specifications, extract_specifications
from .faram_product_specifications import specifications_by_product


def _product_specifications(rows: Iterable[dict[str, str]], product_id: str) -> list[Specification]:
    grouped = specifications_by_product(list(rows), verified_only=True)
    return [
        Specification(
            name=row["specification_name"],
            value=row["specification_value"],
            unit=row.get("specification_unit", ""),
        )
        for row in grouped.get(product_id, [])
    ]


def assess_product(
    requirements_text: str,
    product_id: str,
    specification_rows: Iterable[dict[str, str]],
) -> dict[str, object]:
    """Assess one Faram product against explicitly labelled tender specs."""
    requirements = extract_specifications(requirements_text)
    if not requirements:
        return {
            "product_id": product_id,
            "technical_status": "UNKNOWN",
            "technical_score": 0.0,
            "requirements_count": 0,
            "passed": 0,
            "unknown": 0,
            "failed": 0,
            "rows": [],
            "reason": "No explicitly labelled specification requirements were extracted.",
        }

    comparison = compare_specifications(
        requirements,
        _product_specifications(specification_rows, product_id),
    )
    return {
        "product_id": product_id,
        "technical_status": comparison["overall_status"],
        "technical_score": comparison["score"],
        "requirements_count": len(requirements),
        "passed": comparison["passed"],
        "unknown": comparison["unknown"],
        "failed": comparison["failed"],
        "rows": comparison["rows"],
        "reason": "Verified specification evidence compared deterministically against tender requirements.",
    }


def assess_candidates(
    requirements_text: str,
    candidates: Iterable[dict[str, str]],
    specification_rows: Iterable[dict[str, str]],
) -> list[dict[str, object]]:
    """Add technical specification assessment to existing Faram candidates."""
    rows = list(specification_rows)
    results: list[dict[str, object]] = []
    for candidate in candidates:
        assessment = assess_product(
            requirements_text,
            candidate.get("faram_product_id", ""),
            rows,
        )
        result = dict(candidate)
        result.update({
            "technical_status": assessment["technical_status"],
            "technical_score": assessment["technical_score"],
            "technical_passed": assessment["passed"],
            "technical_unknown": assessment["unknown"],
            "technical_failed": assessment["failed"],
        })
        results.append(result)
    return results
