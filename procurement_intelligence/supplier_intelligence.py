"""Build supplier/competitive intelligence from explicit procurement awards."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from .schema import ProcurementEvent

FIELDS = [
    "supplier", "supplier_country", "award_count", "buyers", "countries",
    "categories", "projects", "latest_award_date", "award_value_total",
    "award_currencies", "faram_relevant_awards", "faram_high_priority_awards",
    "supplier_evidence_status", "competitive_position", "recommended_action",
]


def _split(value: str) -> list[str]:
    return [x.strip() for x in (value or "").split(";") if x.strip()]


def _number(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def build_supplier_history(events: list[ProcurementEvent]) -> list[dict[str, str]]:
    groups: dict[tuple[str, str], dict] = {}
    for event in events:
        if event.supplier_evidence_status != "EXPLICIT" or not event.supplier_name.strip():
            continue
        key = (event.supplier_name.strip(), event.supplier_country.strip())
        group = groups.setdefault(key, {
            "supplier": key[0], "supplier_country": key[1], "events": [],
            "buyers": set(), "countries": set(), "categories": set(), "projects": set(),
            "dates": [], "currencies": set(), "values": defaultdict(float),
        })
        group["events"].append(event)
        if event.buyer: group["buyers"].add(event.buyer.strip())
        if event.country: group["countries"].add(event.country.strip())
        if event.equipment_category: group["categories"].add(event.equipment_category.strip())
        if event.project_reference: group["projects"].add(event.project_reference.strip())
        if event.publication_date: group["dates"].append(event.publication_date)
        currency = (event.award_currency or event.currency or "").strip()
        if currency: group["currencies"].add(currency)
        if currency: group["values"][currency] += _number(event.award_value)

    rows = []
    for group in groups.values():
        events = group["events"]
        relevant = sum(event.faram_relevance_score > 0 for event in events)
        high = sum(event.procurement_priority == "HIGH" for event in events)
        currencies = sorted(group["currencies"])
        value_total = ""
        if len(currencies) == 1:
            value_total = f"{group['values'][currencies[0]]:.2f}"
        position = "INCUMBENT_PATTERN" if len(events) >= 3 else "REPEAT_SUPPLIER" if len(events) >= 2 else "KNOWN_AWARD"
        action = (
            "Investigate incumbent pattern, product/manufacturer coverage and route to compete on the next comparable procurement."
            if len(events) >= 2 else
            "Record as a known awardee and monitor the buyer for comparable future procurement."
        )
        rows.append({
            "supplier": group["supplier"],
            "supplier_country": group["supplier_country"],
            "award_count": str(len(events)),
            "buyers": "; ".join(sorted(group["buyers"])),
            "countries": "; ".join(sorted(group["countries"])),
            "categories": "; ".join(sorted(group["categories"])),
            "projects": "; ".join(sorted(group["projects"])),
            "latest_award_date": max(group["dates"]) if group["dates"] else "",
            "award_value_total": value_total,
            "award_currencies": "; ".join(currencies),
            "faram_relevant_awards": str(relevant),
            "faram_high_priority_awards": str(high),
            "supplier_evidence_status": "EXPLICIT",
            "competitive_position": position,
            "recommended_action": action,
        })
    return sorted(rows, key=lambda row: (-int(row["award_count"]), row["supplier"].lower()))


def write_supplier_history(path: Path, events: list[ProcurementEvent]) -> int:
    rows = build_supplier_history(events)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
