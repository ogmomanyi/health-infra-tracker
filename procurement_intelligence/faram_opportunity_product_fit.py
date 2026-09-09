"""Build tender-level technical fit intelligence from controlled Faram matches."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from .faram_product_specifications import load_specifications
from .faram_specification_matching import assess_candidates

OUTPUT_FIELDS = [
    "procurement_event_id", "tender_reference", "title", "buyer", "country",
    "faram_product_id", "product_name", "manufacturer_name", "match_status",
    "match_confidence", "technical_status", "technical_score", "technical_passed",
    "technical_unknown", "technical_failed", "technical_action",
]


def load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _requirements_text(row: dict[str, str]) -> str:
    """Use only tender text already present; never manufacture requirements."""
    return " | ".join(
        str(row.get(field, "") or "").strip()
        for field in ("title", "product_family", "equipment_category")
        if str(row.get(field, "") or "").strip()
    )


def build_fit(rows: list[dict[str, str]], specification_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for row in rows:
        candidate = dict(row)
        assessment = assess_candidates(
            _requirements_text(row), [candidate], specification_rows
        )[0]
        technical_status = str(assessment["technical_status"])
        action = {
            "PASS": "Technical evidence supports the explicitly extracted requirements; proceed to detailed bid compliance review.",
            "REVIEW": "Technical evidence is incomplete or mixed; obtain/verify the missing specification evidence before bid commitment.",
            "FAIL": "Verified technical evidence conflicts with an explicit requirement; do not treat this candidate as technically compliant.",
            "UNKNOWN": "No sufficient explicit technical requirement/evidence was available; obtain the tender specification and verify the product datasheet.",
        }[technical_status]
        results.append({
            "procurement_event_id": str(row.get("procurement_event_id", "")),
            "tender_reference": str(row.get("tender_reference", "")),
            "title": str(row.get("title", "")),
            "buyer": str(row.get("buyer", "")),
            "country": str(row.get("country", "")),
            "faram_product_id": str(row.get("faram_product_id", "")),
            "product_name": str(row.get("product_name", "")),
            "manufacturer_name": str(row.get("manufacturer_name", "")),
            "match_status": str(row.get("match_status", "")),
            "match_confidence": str(row.get("match_confidence", "")),
            "technical_status": technical_status,
            "technical_score": str(assessment["technical_score"]),
            "technical_passed": str(assessment["passed"]),
            "technical_unknown": str(assessment["unknown"]),
            "technical_failed": str(assessment["failed"]),
            "technical_action": action,
        })
    return results


def write_output(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--faram-matches", default="data/faram_product_matches.csv")
    parser.add_argument("--specifications", default="data/faram_product_specifications.csv")
    parser.add_argument("--output", default="data/faram_opportunity_product_fit.csv")
    args = parser.parse_args()
    rows = build_fit(load_rows(Path(args.faram_matches)), load_specifications(Path(args.specifications)))
    write_output(Path(args.output), rows)
    print(f"Faram opportunity product fit completed: {len(rows)} candidate assessments")


if __name__ == "__main__":
    main()
