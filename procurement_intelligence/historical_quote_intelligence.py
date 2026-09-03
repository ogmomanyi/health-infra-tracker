"""Historical Faram quotation intelligence.

This layer captures prior commercial familiarity only. It must never be treated
as proof of current representation, territory authorization, or principal
status.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable


SUMMARY_FIELDS = [
    "product_family",
    "product_name",
    "manufacturer_name",
    "model",
    "historical_quote_count",
    "supplier_count",
    "evidence_strength",
    "source_evidence_ids",
    "historical_status",
]

_EVIDENCE_WEIGHTS = {
    "quotation_and_tender_support": 4,
    "tender_fit_and_pricing": 4,
    "order_and_business_review": 5,
    "quotation": 3,
    "quotation_inquiry": 3,
    "tender_compliance_and_quotation": 4,
    "quotation_and_technical_support": 3,
    "tender_support": 3,
    "market_evaluation_and_pricing": 2,
    "partnership_and_tender_support": 2,
    "project_inquiry": 2,
    "procurement_inquiry": 2,
    "request_for_pricing": 2,
}


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def normalize(value: object) -> str:
    text = _text(value).lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def contains_phrase(text: object, phrase: object) -> bool:
    haystack = normalize(text)
    needle = normalize(phrase)
    if not haystack or not needle:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None


def load_evidence(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def build_summary(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    groups: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        # External procurement requests are demand evidence, not historical
        # Faram quotation evidence. Keep them available in the raw evidence file
        # but exclude them from the familiarity summary.
        if _text(row.get("evidence_id")) == "HQE-005":
            continue
        key = (
            _text(row.get("product_family")),
            _text(row.get("product_name")),
            _text(row.get("manufacturer_name")),
            _text(row.get("model")),
        )
        groups[key].append(row)

    summary: list[dict[str, str]] = []
    for (family, product, manufacturer, model), items in groups.items():
        suppliers = {normalize(item.get("supplier_email")) for item in items if _text(item.get("supplier_email"))}
        weight = sum(_EVIDENCE_WEIGHTS.get(normalize(item.get("evidence_type")), 1) for item in items)
        strength = "HIGH" if weight >= 7 or len(items) >= 3 else "MEDIUM" if weight >= 3 else "LOW"
        summary.append({
            "product_family": family,
            "product_name": product,
            "manufacturer_name": manufacturer,
            "model": model,
            "historical_quote_count": str(len(items)),
            "supplier_count": str(len(suppliers)),
            "evidence_strength": strength,
            "source_evidence_ids": "; ".join(_text(item.get("evidence_id")) for item in items if _text(item.get("evidence_id"))),
            "historical_status": "HISTORICAL_COMMERCIAL_EVIDENCE",
        })

    return sorted(summary, key=lambda row: (-int(row["historical_quote_count"]), row["product_family"].lower(), row["product_name"].lower()))


def write_summary(path: Path, rows: Iterable[dict[str, str]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = build_summary(rows)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(summary)
    return len(summary)


def familiarity_match(
    project_title: object,
    description: object,
    product_family: object,
    manufacturer_mentions: object,
    evidence_rows: Iterable[dict[str, str]],
) -> dict[str, object]:
    """Score explicit overlap between an opportunity and historical Faram evidence.

    Scores are intentionally small and additive. No match is inferred from a
    manufacturer/category relationship unless the relevant term is explicitly
    present in the opportunity text.
    """
    opportunity_text = f"{_text(project_title)} {_text(description)} {_text(manufacturer_mentions)}"
    opportunity_family = normalize(product_family)
    candidates: list[tuple[int, dict[str, str], list[str]]] = []

    for row in evidence_rows:
        if normalize(row.get("evidence_id")) == "hqe 005":
            continue
        evidence: list[str] = []
        score = 0
        family = _text(row.get("product_family"))
        manufacturer = _text(row.get("manufacturer_name"))
        product = _text(row.get("product_name"))
        model = _text(row.get("model"))

        if family and opportunity_family and normalize(family) == opportunity_family:
            score += 2
            evidence.append("product_family")
        if manufacturer and contains_phrase(opportunity_text, manufacturer):
            score += 3
            evidence.append("manufacturer")
        if product and contains_phrase(opportunity_text, product):
            score += 3
            evidence.append("product")
        if model and contains_phrase(opportunity_text, model):
            score += 2
            evidence.append("model")

        if score:
            candidates.append((score, row, evidence))

    if not candidates:
        return {
            "historical_familiarity_score": 0.0,
            "historical_familiarity_band": "NONE",
            "historical_familiarity_status": "NO_HISTORICAL_MATCH",
            "historical_familiarity_evidence": "",
            "historical_evidence_ids": "",
        }

    # Repeated records strengthen confidence, but the overall contribution is capped.
    candidates.sort(key=lambda item: item[0], reverse=True)
    best_score, best_row, best_evidence = candidates[0]
    repeat_bonus = min(3, max(0, len(candidates) - 1))
    familiarity = min(10.0, float(best_score + repeat_bonus))

    if "model" in best_evidence or "product" in best_evidence:
        band = "EXACT"
    elif "manufacturer" in best_evidence:
        band = "MANUFACTURER"
    elif "product_family" in best_evidence:
        band = "FAMILY"
    else:
        band = "SIGNAL"

    ids = []
    for _, row, _ in candidates:
        evidence_id = _text(row.get("evidence_id"))
        if evidence_id and evidence_id not in ids:
            ids.append(evidence_id)

    return {
        "historical_familiarity_score": round(familiarity, 1),
        "historical_familiarity_band": band,
        "historical_familiarity_status": "HISTORICAL_COMMERCIAL_EVIDENCE",
        "historical_familiarity_evidence": "; ".join(best_evidence),
        "historical_evidence_ids": "; ".join(ids),
    }


def enrich_opportunity(row: dict[str, object], evidence_rows: Iterable[dict[str, str]]) -> dict[str, object]:
    return familiarity_match(
        row.get("project_title"),
        row.get("description"),
        row.get("product_family") or row.get("direct_equipment_categories") or row.get("equipment_target_summary"),
        row.get("manufacturer_mentions"),
        evidence_rows,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Summarize historical Faram quotation evidence.")
    parser.add_argument("--evidence", default="data/faram_historical_quote_evidence.csv")
    parser.add_argument("--output", default="data/faram_historical_quote_summary.csv")
    args = parser.parse_args()

    rows = load_evidence(Path(args.evidence))
    count = write_summary(Path(args.output), rows)
    print(f"Historical quote summary completed: {count} grouped records")


if __name__ == "__main__":
    main()
