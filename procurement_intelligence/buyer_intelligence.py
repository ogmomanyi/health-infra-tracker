"""Buyer demand intelligence derived from external procurement events.

This layer answers: which organisations are actively buying, how much demand
is visible, and how commercially important is each buyer? It deliberately does
not claim that Faram represents the buyer's required products.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from organisation_resolution.normalizer import normalize_name

from .ingest import read_events


COMMERCIAL_CATEGORIES = {
    "Laboratory Equipment",
    "Diagnostics",
    "Medical Equipment",
    "Blood Banking",
    "Cold Chain",
    "Sterilization",
    "PPE",
    "Ophthalmology",
    "Laboratory Consumables",
}

BUYER_FIELDS = [
    "buyer",
    "country",
    "entity_id",
    "canonical_buyer",
    "buyer_match_status",
    "buyer_match_confidence",
    "raw_buyer_names",
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
    "recurring_categories",
    "linked_projects",
    "buyer_demand_score",
    "buyer_demand_tier",
    "recommended_action",
]


def _number(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _date(value: str) -> date | None:
    try:
        return date.fromisoformat((value or "").strip())
    except (TypeError, ValueError):
        return None


def _canonical_root(conn, entity_id: str) -> str:
    """Follow DUPLICATE_OF links without mutating the canonical registry."""
    current = entity_id
    visited: set[str] = set()
    try:
        while current:
            if current in visited:
                raise RuntimeError(f"Cycle detected in organisation relationships at {current}")
            visited.add(current)
            row = conn.execute(
                """
                SELECT parent_entity_id
                FROM organisation_relationships
                WHERE child_entity_id = ?
                  AND relationship_type = 'DUPLICATE_OF'
                """,
                (current,),
            ).fetchone()
            if not row:
                break
            current = row[0]
    except sqlite3.OperationalError:
        return entity_id
    return current


def load_buyer_resolution_index(database: str | Path | None) -> dict:
    """Load exact canonical names and unambiguous aliases from SQLite."""
    empty = {"names": {}, "canonical_names": {}, "alias_names": {}}
    if database is None:
        return empty
    database = Path(database)
    if not database.exists():
        return empty

    with sqlite3.connect(database) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "organisation_entities" not in tables or "organisation_aliases" not in tables:
            return empty

        canonical_rows = conn.execute(
            """
            SELECT entity_id, canonical_name
            FROM organisation_entities
            WHERE entity_status = 'ACTIVE'
            """
        ).fetchall()
        alias_rows = conn.execute(
            """
            SELECT a.entity_id, a.alias_name
            FROM organisation_aliases a
            JOIN organisation_entities e ON e.entity_id = a.entity_id
            WHERE e.entity_status = 'ACTIVE'
            """
        ).fetchall()

        canonical_names: dict[str, str] = {}
        entity_names: dict[str, set[str]] = defaultdict(set)
        for entity_id, canonical_name in canonical_rows:
            root = _canonical_root(conn, entity_id)
            normalized = normalize_name(canonical_name)
            if normalized:
                canonical_names[normalized] = root
            entity_names[root].add(canonical_name)

        alias_to_entities: dict[str, set[str]] = defaultdict(set)
        for entity_id, alias_name in alias_rows:
            normalized = normalize_name(alias_name)
            if normalized:
                alias_to_entities[normalized].add(_canonical_root(conn, entity_id))

        alias_names = {
            normalized: next(iter(entity_ids))
            for normalized, entity_ids in alias_to_entities.items()
            if len(entity_ids) == 1
        }
        names = dict(canonical_names)
        for normalized, entity_id in alias_names.items():
            names.setdefault(normalized, entity_id)

        canonical_by_entity = {
            entity_id: min(names_list, key=lambda value: normalize_name(value))
            for entity_id, names_list in entity_names.items()
            if names_list
        }
        for entity_id, canonical_name in canonical_rows:
            root = _canonical_root(conn, entity_id)
            canonical_by_entity.setdefault(root, canonical_name)
            if root == entity_id:
                canonical_by_entity[root] = canonical_name

    return {"names": names, "canonical_names": canonical_by_entity, "alias_names": alias_names}


def _resolve_buyer(raw_buyer: str, index: dict) -> tuple[str, str, str, float]:
    raw = (raw_buyer or "").strip()
    normalized = normalize_name(raw)
    if not normalized:
        return "", "", "UNMATCHED", 0.0

    entity_id = index.get("names", {}).get(normalized)
    if not entity_id:
        return "", raw, "UNMATCHED", 0.0

    canonical = index.get("canonical_names", {}).get(entity_id, raw)
    status = "CANONICAL_EXACT" if normalized == normalize_name(canonical) else "ALIAS_EXACT"
    return entity_id, canonical, status, 1.0


def _buyer_demand_score(items: list, recurring_categories: list[str], today: date) -> float:
    active = sum(e.opportunity_status == "ACTIVE_OPPORTUNITY" for e in items)
    high = sum(e.procurement_priority == "HIGH" for e in items)
    relevant = sum(e.equipment_category in COMMERCIAL_CATEGORIES for e in items)
    awards = sum(e.opportunity_status == "AWARD_HISTORY" for e in items)
    iati = sum(bool(e.matched_iati_identifier) for e in items)
    recent = sum(
        1
        for event in items
        if (published := _date(event.publication_date))
        and 0 <= (today - published).days <= 90
    )

    values = sum(_number(e.estimated_value) for e in items)
    score = 0.0
    score += min(20.0, active * 5.0)
    score += min(15.0, high * 5.0)
    score += min(15.0, relevant * 3.0)
    score += min(10.0, len(recurring_categories) * 5.0)
    score += min(10.0, awards * 2.0)
    score += min(10.0, iati * 2.0)
    score += min(10.0, recent * 2.0)
    if values >= 1_000_000:
        score += 10.0
    elif values >= 250_000:
        score += 7.0
    elif values >= 50_000:
        score += 4.0
    elif values > 0:
        score += 2.0
    return round(min(100.0, score), 1)


def _buyer_demand_tier(score: float) -> str:
    if score >= 70:
        return "A"
    if score >= 45:
        return "B"
    if score >= 20:
        return "C"
    return "MONITOR"


def _recommended_action(tier: str, active: int, plans: int, gpn: int, awards: int) -> str:
    if tier == "A" and active:
        return "Engage now: qualify the opportunity, confirm bid route, and mobilize the tender/technical team."
    if tier == "A" and (plans or gpn):
        return "Pre-position: map stakeholders, procurement route and product fit before the next notice."
    if tier == "B" and active:
        return "Pursue: review active notices and establish the buyer/procurement contact path."
    if tier == "B" and (plans or gpn):
        return "Develop account: track the pipeline and prepare relevant product/manufacturer coverage."
    if awards:
        return "Research incumbent pattern and monitor for the buyer's next comparable procurement."
    if tier == "C":
        return "Monitor: retain the account on the watchlist and review new procurement signals."
    return "Monitor."


def _iati_project_index(database: str | Path | None) -> dict[str, str]:
    if database is None:
        return {}
    database = Path(database)
    if not database.exists():
        return {}
    try:
        with sqlite3.connect(database) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "activities" not in tables:
                return {}
            columns = {row[1] for row in conn.execute("PRAGMA table_info(activities)")}
            if "iati_identifier" not in columns:
                return {}
            selected = [
                field for field in (
                    "iati_identifier", "project_title", "project_name", "activity_title", "activity_ref"
                ) if field in columns
            ]
            rows = conn.execute(
                "SELECT " + ", ".join(f'\"{field}\"' for field in selected) + " FROM activities"
            ).fetchall()
    except sqlite3.Error:
        return {}

    index: dict[str, str] = {}
    positions = {field: i for i, field in enumerate(selected)}
    for row in rows:
        identifier = str(row[positions["iati_identifier"]] or "").strip()
        if not identifier:
            continue
        title = ""
        for field in ("project_title", "project_name", "activity_title", "activity_ref"):
            if field in positions and row[positions[field]]:
                title = str(row[positions[field]]).strip()
                if title:
                    break
        index[identifier] = title
    return index


def build_buyer_history(events, database: str | Path | None = None, today: date | None = None) -> list[dict[str, str]]:
    """Aggregate external procurement into buyer-level demand intelligence."""
    today = today or date.today()
    resolution_index = load_buyer_resolution_index(database)
    iati_projects = _iati_project_index(database)

    grouped: dict[tuple[str, str], list] = defaultdict(list)
    metadata: dict[tuple[str, str], dict] = {}

    for event in events:
        raw_buyer = (event.buyer or "").strip()
        country = (event.country or "").strip()
        if not raw_buyer:
            continue

        entity_id, canonical, match_status, confidence = _resolve_buyer(raw_buyer, resolution_index)
        group_key = (entity_id or f"RAW:{normalize_name(raw_buyer)}", country)
        grouped[group_key].append(event)
        meta = metadata.setdefault(
            group_key,
            {
                "entity_id": entity_id,
                "canonical": canonical or raw_buyer,
                "match_status": match_status,
                "confidence": confidence,
                "raw_names": set(),
            },
        )
        meta["raw_names"].add(raw_buyer)
        if entity_id:
            meta["canonical"] = canonical

    rows: list[dict[str, str]] = []
    for key, items in grouped.items():
        meta = metadata[key]
        category_counts = Counter(e.equipment_category for e in items if e.equipment_category)
        recurring_categories = sorted(
            category for category, count in category_counts.items() if count >= 2
        )
        linked_ids = [e.matched_iati_identifier for e in items if e.matched_iati_identifier]
        linked_projects = sorted({
            iati_projects.get(identifier, identifier)
            for identifier in linked_ids
            if iati_projects.get(identifier, identifier)
        })
        publications = [e.publication_date for e in items if e.publication_date]
        closings = [
            parsed
            for event in items
            if event.closing_date and (parsed := _date(event.closing_date))
        ]
        high = sum(e.procurement_priority == "HIGH" for e in items)
        active = sum(e.opportunity_status == "ACTIVE_OPPORTUNITY" for e in items)
        plans = sum(e.opportunity_status == "PROCUREMENT_PLAN" for e in items)
        gpn = sum(e.opportunity_status == "UPCOMING_GPN" for e in items)
        awards = sum(e.opportunity_status == "AWARD_HISTORY" for e in items)
        score = _buyer_demand_score(items, recurring_categories, today)
        tier = _buyer_demand_tier(score)
        canonical = meta["canonical"]

        rows.append({
            "buyer": canonical,
            "country": key[1],
            "entity_id": meta["entity_id"],
            "canonical_buyer": canonical,
            "buyer_match_status": meta["match_status"],
            "buyer_match_confidence": f"{meta['confidence']:.3f}",
            "raw_buyer_names": "; ".join(sorted(meta["raw_names"])),
            "event_count": str(len(items)),
            "active_opportunities": str(active),
            "upcoming_gpn": str(gpn),
            "procurement_plans": str(plans),
            "award_history": str(awards),
            "high_priority_opportunities": str(high),
            "estimated_value_total": f"{sum(_number(e.estimated_value) for e in items):.2f}",
            "latest_publication_date": max(publications) if publications else "",
            "next_closing_date": min(closings).isoformat() if closings else "",
            "iati_linked_events": str(len(linked_ids)),
            "project_count": str(len(set(linked_ids))),
            "sources": "; ".join(sorted({e.source for e in items if e.source})),
            "categories": "; ".join(sorted(category_counts)),
            "recurring_categories": "; ".join(recurring_categories),
            "linked_projects": "; ".join(linked_projects),
            "buyer_demand_score": f"{score:.1f}",
            "buyer_demand_tier": tier,
            "recommended_action": _recommended_action(tier, active, plans, gpn, awards),
        })

    return sorted(
        rows,
        key=lambda row: (
            -float(row["buyer_demand_score"]),
            -int(row["active_opportunities"]),
            -int(row["high_priority_opportunities"]),
            -int(row["award_history"]),
            row["buyer"].lower(),
        ),
    )


def write_buyer_history(
    path: str | Path,
    events,
    database: str | Path | None = None,
    today: date | None = None,
) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = build_buyer_history(events, database=database, today=today)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=BUYER_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build buyer-level procurement demand intelligence.")
    parser.add_argument("--events", default="data/procurement_events.csv")
    parser.add_argument("--database", default="data/iati_intelligence.db")
    parser.add_argument("--output", default="data/procurement_buyer_history.csv")
    args = parser.parse_args()

    events = list(read_events(args.events))
    count = write_buyer_history(args.output, events, database=args.database)
    print(f"Buyer demand intelligence generated: {count} buyer accounts")


if __name__ == "__main__":
    main()
