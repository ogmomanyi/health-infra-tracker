"""Deterministic specification extraction and comparison for tender matching.

This layer is deliberately evidence-first: it extracts only explicitly labelled
requirements and compares normalized values without inventing missing specs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Specification:
    name: str
    value: float | str
    unit: str = ""


_UNIT_FACTORS = {
    "ml": ("ml", 1.0), "l": ("ml", 1000.0), "ul": ("ml", 0.001),
    "µl": ("ml", 0.001), "μl": ("ml", 0.001),
    "tests/hour": ("tests/hour", 1.0), "tests/hr": ("tests/hour", 1.0),
    "t/h": ("tests/hour", 1.0), "nm": ("nm", 1.0),
}


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" \t\r\n:;-|,.")


def _number(value: str) -> float | None:
    try:
        return float(value.replace(",", ""))
    except (TypeError, ValueError):
        return None


def _normalize_unit(unit: str) -> tuple[str, float]:
    key = _clean(unit).lower()
    return _UNIT_FACTORS.get(key, (key, 1.0))


def _normalize_value(value: str, unit: str) -> tuple[float | str, str]:
    numeric = _number(value)
    normalized_unit, factor = _normalize_unit(unit)
    if numeric is not None:
        return numeric * factor, normalized_unit
    return _clean(value).casefold(), normalized_unit


def _normalize_specification(specification: Specification) -> Specification:
    value, unit = _normalize_value(str(specification.value), specification.unit)
    return Specification(_clean(specification.name).casefold(), value, unit)


def extract_specifications(text: str) -> list[Specification]:
    """Extract explicitly labelled ``spec: value [unit]`` requirements."""
    if not text:
        return []
    results: list[Specification] = []
    units = r"ml|l|uL|µL|μL|tests/hour|tests/hr|t/h|nm"
    pattern = re.compile(
        rf"(?:^|[;\n|])\s*([A-Za-z][A-Za-z0-9 /_-]{{1,50}})\s*[:=]\s*"
        rf"(?:(?P<num>[0-9]+(?:[.,][0-9]+)?)\s*(?P<num_unit>{units})|"
        rf"(?P<text>[A-Za-z0-9][A-Za-z0-9 .+/%-]{{0,60}}?))\s*(?=$|[;\n|])",
        re.I,
    )
    seen: set[tuple[str, str, str]] = set()
    for match in pattern.finditer(text):
        name = _clean(match.group(1)).casefold()
        raw_value = _clean(match.group("num") or match.group("text") or "")
        raw_unit = _clean(match.group("num_unit") or "")
        value, unit = _normalize_value(raw_value, raw_unit)
        key = (name, str(value), unit)
        if key not in seen:
            seen.add(key)
            results.append(Specification(name, value, unit))
    return results


def specifications_map(specifications: Iterable[Specification]) -> dict[str, Specification]:
    return {normalized.name: normalized for normalized in (_normalize_specification(item) for item in specifications)}


def compare_specifications(requirements: Iterable[Specification], product_specs: Iterable[Specification]) -> dict[str, object]:
    """Compare requirements against explicit product specs."""
    normalized_requirements = [_normalize_specification(item) for item in requirements]
    product = specifications_map(product_specs)
    rows: list[dict[str, object]] = []
    for requirement in normalized_requirements:
        candidate = product.get(requirement.name)
        if candidate is None:
            status = "UNKNOWN"
        elif isinstance(requirement.value, (int, float)) and isinstance(candidate.value, (int, float)):
            if requirement.unit != candidate.unit:
                status = "UNKNOWN"
            else:
                minimum = any(token in requirement.name for token in ("throughput", "capacity", "speed", "tests", "samples"))
                status = "PASS" if (candidate.value >= requirement.value if minimum else candidate.value == requirement.value) else "FAIL"
        else:
            status = "PASS" if str(candidate.value).casefold() == str(requirement.value).casefold() and requirement.unit == candidate.unit else "FAIL"
        rows.append({"requirement": requirement.name, "required_value": requirement.value, "required_unit": requirement.unit, "product_value": candidate.value if candidate else "", "product_unit": candidate.unit if candidate else "", "status": status})
    total = len(rows)
    passed = sum(row["status"] == "PASS" for row in rows)
    unknown = sum(row["status"] == "UNKNOWN" for row in rows)
    failed = sum(row["status"] == "FAIL" for row in rows)
    score = round((passed / total) * 100, 1) if total else 0.0
    overall = "PASS" if total and failed == 0 and unknown == 0 else "REVIEW" if passed or unknown else "FAIL"
    return {"rows": rows, "score": score, "overall_status": overall, "passed": passed, "unknown": unknown, "failed": failed}
