"""Build supplier/competitive intelligence from explicit procurement awards."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from .schema import ProcurementEvent

FIELDS = [
    "supplier_entity_id", "supplier", "supplier_country", "supplier_match_status",
    "supplier_match_confidence", "award_count", "buyers", "countries", "categories",
    "projects", "latest_award_date", "award_value_total", "award_currencies",
    "faram_relevant_awards", "faram_high_priority_awards", "supplier_evidence_status",
    "competitive_position", "recommended_action",
]


def _number(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def build_supplier_history(events: list[ProcurementEvent]) -> list[dict[str, str]]:
    """Aggregate explicit awards by canonical supplier entity where resolved.

    Resolved awards are grouped by entity ID and country, so approved aliases
    collapse into one supplier record. Unresolved suppliers remain grouped by
    raw name and country so no evidence is lost or silently merged.
    """
    groups: dict[tuple[str, str, str], dict] = {}
    for event in events:
        if event.supplier_evidence_status != "EXPLICIT" or not event.supplier_name.strip():
            continue
        country = event.supplier_country.strip()
        entity_id = event.supplier_entity_id.strip()
        key = (entity_id, country, "") if entity_id else ("", country, event.supplier_name.strip())
        group = groups.setdefault(key, {
            "entity_id": entity_id,
            "supplier": event.supplier_canonical_name.strip() or event.supplier_name.strip(),
            "supplier_country": country,
            "match_status": event.supplier_match_status or ("CANONICAL_EXACT" if entity_id else "UNRESOLVED"),
            "match_confidence": event.supplier_match_confidence,
            "events": [], "buyers": set(), "countries": set(), "categories": set(),
            "projects": set(), "dates": [], "currencies": set(), "values": defaultdict(float),
        })
        group["events"].append(event)
        if event.supplier_canonical_name.strip():
            group["supplier"] = event.supplier_canonical_name.strip()
        if event.buyer: group["buyers"].add(event.buyer.strip())
        if event.country: group["countries"].add(event.country.strip())
        if event.equipment_category: group["categories"].add(event.equipment_category.strip())
        if event.project_reference: group["projects"].add(event.project_reference.strip())
        if event.publication_date: group["dates"].append(event.publication_date)
        group["match_confidence"] = max(float(group["match_confidence"] or 0), float(event.supplier_match_confidence or 0))
        currency = (event.award_currency or event.currency or "").strip()
        if currency:
            group["currencies"].add(currency)
            group["values"][currency] += _number(event.award_value)

    rows = []
    for group in groups.values():
        awards = group["events"]
        relevant = sum(event.faram_relevance_score > 0 for event in awards)
        high = sum(event.procurement_priority == "HIGH" for event in awards)
        currencies = sorted(group["currencies"])
        value_total = f"{group['values'][currencies[0]]:.2f}" if len(currencies) == 1 else ""
        position = "INCUMBENT_PATTERN" if len(awards) >= 3 else "REPEAT_SUPPLIER" if len(awards) >= 2 else "KNOWN_AWARD"
        action = (
            "Investigate incumbent pattern, product/manufacturer coverage and route to compete on the next comparable procurement."
            if len(awards) >= 2 else
            "Record as a known awardee and monitor the buyer for comparable future procurement."
        )
        rows.append({
            "supplier_entity_id": group["entity_id"],
            "supplier": group["supplier"],
            "supplier_country": group["supplier_country"],
            "supplier_match_status": group["match_status"],
            "supplier_match_confidence": f"{float(group['match_confidence']):.2f}",
            "award_count": str(len(awards)),
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
