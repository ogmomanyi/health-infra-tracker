"""Commercial intelligence derived from external procurement events."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


BUYER_FIELDS = [
    "buyer",
    "country",
    "event_count",
    "active_opportunities",
    "upcoming_gpn",
    "procurement_plans",
    "award_history",
    "high_priority_opportunities",
    "estimated_value_total",
    "latest_publication_date",
    "next_closing_date",
    "iati_linked_events",
    "project_count",
    "sources",
    "categories",
]


def _number(value: str) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def build_buyer_history(events) -> list[dict[str, str]]:
    """Aggregate procurement activity by buyer and country.

    Blank buyers are excluded rather than inventing an organization name.
    Metrics combine current opportunities, forward-looking planning signals,
    and award/history records so the same table supports account research.
    """
    grouped: dict[tuple[str, str], list] = defaultdict(list)
    for event in events:
        buyer = (event.buyer or "").strip()
        country = (event.country or "").strip()
        if not buyer:
            continue
        grouped[(buyer, country)].append(event)

    rows: list[dict[str, str]] = []
    for (buyer, country), items in grouped.items():
        publications = [e.publication_date for e in items if e.publication_date]
        closings = [e.closing_date for e in items if e.closing_date]
        projects = {e.project_reference for e in items if e.project_reference}
        sources = {e.source for e in items if e.source}
        categories = {e.equipment_category for e in items if e.equipment_category}
        rows.append({
            "buyer": buyer,
            "country": country,
            "event_count": str(len(items)),
            "active_opportunities": str(sum(e.opportunity_status == "ACTIVE_OPPORTUNITY" for e in items)),
            "upcoming_gpn": str(sum(e.opportunity_status == "UPCOMING_GPN" for e in items)),
            "procurement_plans": str(sum(e.opportunity_status == "PROCUREMENT_PLAN" for e in items)),
            "award_history": str(sum(e.opportunity_status == "AWARD_HISTORY" for e in items)),
            "high_priority_opportunities": str(sum(e.procurement_priority == "HIGH" for e in items)),
            "estimated_value_total": f"{sum(_number(e.estimated_value) for e in items):.2f}",
            "latest_publication_date": max(publications) if publications else "",
            "next_closing_date": min(closings) if closings else "",
            "iati_linked_events": str(sum(bool(e.matched_iati_identifier) for e in items)),
            "project_count": str(len(projects)),
            "sources": "; ".join(sorted(sources)),
            "categories": "; ".join(sorted(categories)),
        })

    return sorted(
        rows,
        key=lambda row: (
            -int(row["high_priority_opportunities"]),
            -int(row["active_opportunities"]),
            -int(row["award_history"]),
            -int(row["event_count"]),
            row["buyer"].lower(),
        ),
    )


def write_buyer_history(path: str | Path, events) -> int:
    """Write buyer-level procurement history as a dashboard-friendly CSV."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = build_buyer_history(events)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=BUYER_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
