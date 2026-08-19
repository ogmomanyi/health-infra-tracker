"""
Opportunity Organisation Resolution

Resolves organisation references appearing in opportunity_intelligence
against the existing 03B organisation entity/alias layer.

This module does NOT modify the database.
It produces resolution decisions only.
"""

import sqlite3

from organisation_resolution.database_resolver import (
    get_canonical_entity_id,
    load_alias_candidates,
    load_entity_candidates,
)
from organisation_resolution.normalizer import normalize_name


NON_ENTITY_NAMES = {
    "anonymous",
    "ip not published",
    "undefined",
}


def split_values(value):
    if not value:
        return []

    return [
        item.strip()
        for item in str(value).split(";")
        if item.strip()
    ]


def build_indexes(conn):
    """
    Build lookup indexes from the existing 03B entity/alias layer.
    """

    entity_rows = conn.execute("""
        SELECT entity_id, canonical_name
        FROM organisation_entities
        WHERE entity_status = 'ACTIVE'
    """).fetchall()

    entities_by_name = {}

    for entity_id, canonical_name in entity_rows:
        normalized = normalize_name(canonical_name)

        if normalized:
            entities_by_name.setdefault(
                normalized,
                set()
            ).add(entity_id)

    alias_rows = conn.execute("""
        SELECT
            alias_name,
            entity_id,
            organisation_key,
            org_ref,
            match_method,
            confidence_score
        FROM organisation_aliases
    """).fetchall()

    aliases_by_name = {}

    for (
        alias_name,
        entity_id,
        organisation_key,
        org_ref,
        match_method,
        confidence_score,
    ) in alias_rows:

        normalized = normalize_name(alias_name)

        if not normalized:
            continue

        aliases_by_name.setdefault(
            normalized,
            set()
        ).add(entity_id)

    return {
        "entities_by_name": entities_by_name,
        "aliases_by_name": aliases_by_name,
    }


def resolve_name(conn, value, indexes):
    """
    Resolve one opportunity organisation name.

    Resolution order:

    1. Known non-entity
    2. Exact normalized canonical name
    3. Exact normalized alias
    4. Unresolved
    """

    normalized = normalize_name(value)

    if not normalized:
        return {
            "entity_id": None,
            "resolution_status": "UNRESOLVED",
            "match_method": None,
            "confidence_score": 0.0,
        }

    if normalized in NON_ENTITY_NAMES:
        return {
            "entity_id": None,
            "resolution_status": "NON_ENTITY",
            "match_method": "NON_ENTITY",
            "confidence_score": 0.0,
        }

    entity_matches = indexes["entities_by_name"].get(
        normalized,
        set()
    )

    if len(entity_matches) == 1:

        entity_id = next(iter(entity_matches))

        entity_id = get_canonical_entity_id(
            conn,
            entity_id,
        )

        return {
            "entity_id": entity_id,
            "resolution_status": "RESOLVED",
            "match_method": "CANONICAL_EXACT",
            "confidence_score": 1.0,
        }

    alias_matches = indexes["aliases_by_name"].get(
        normalized,
        set()
    )

    if len(alias_matches) == 1:

        entity_id = next(iter(alias_matches))

        entity_id = get_canonical_entity_id(
            conn,
            entity_id,
        )

        return {
            "entity_id": entity_id,
            "resolution_status": "RESOLVED",
            "match_method": "ALIAS_EXACT",
            "confidence_score": 1.0,
        }

    if len(entity_matches) > 1 or len(alias_matches) > 1:
        return {
            "entity_id": None,
            "resolution_status": "AMBIGUOUS",
            "match_method": None,
            "confidence_score": 0.0,
        }

    return {
        "entity_id": None,
        "resolution_status": "UNRESOLVED",
        "match_method": None,
        "confidence_score": 0.0,
    }


def load_opportunity_references(conn):
    """
    Return every organisation reference appearing in an opportunity.

    Relationship types:

    funding
    implementing
    reporting
    """

    rows = conn.execute("""
        SELECT
            opportunity_id,
            funding_agencies,
            implementing_partners,
            reporting_org_name
        FROM opportunity_intelligence
        ORDER BY opportunity_id
    """).fetchall()

    references = []

    for (
        opportunity_id,
        funding_agencies,
        implementing_partners,
        reporting_org_name,
    ) in rows:

        for name in split_values(funding_agencies):
            references.append({
                "opportunity_id": opportunity_id,
                "organisation_name": name,
                "relationship_type": "funding",
            })

        for name in split_values(implementing_partners):
            references.append({
                "opportunity_id": opportunity_id,
                "organisation_name": name,
                "relationship_type": "implementing",
            })

        reporting = (
            str(reporting_org_name).strip()
            if reporting_org_name
            else ""
        )

        if reporting:
            references.append({
                "opportunity_id": opportunity_id,
                "organisation_name": reporting,
                "relationship_type": "reporting",
            })

    return references


def resolve_opportunity_references(conn):
    indexes = build_indexes(conn)
    references = load_opportunity_references(conn)

    decisions = []

    for reference in references:

        result = resolve_name(
            conn,
            reference["organisation_name"],
            indexes,
        )

        decisions.append({
            **reference,
            **result,
        })

    return decisions


def print_audit(decisions):
    total = len(decisions)

    resolved = [
        d for d in decisions
        if d["resolution_status"] == "RESOLVED"
    ]

    unresolved = [
        d for d in decisions
        if d["resolution_status"] == "UNRESOLVED"
    ]

    ambiguous = [
        d for d in decisions
        if d["resolution_status"] == "AMBIGUOUS"
    ]

    non_entities = [
        d for d in decisions
        if d["resolution_status"] == "NON_ENTITY"
    ]

    print()
    print("=== OPPORTUNITY ORGANISATION RESOLUTION AUDIT ===")
    print()
    print(f"Total references:       {total:,}")
    print(f"Resolved:               {len(resolved):,}")
    print(f"Unresolved:             {len(unresolved):,}")
    print(f"Ambiguous:              {len(ambiguous):,}")
    print(f"Non-entity:             {len(non_entities):,}")

    if total:
        print(
            f"Resolution rate:        "
            f"{len(resolved) / total:.1%}"
        )

    print()
    print("=== UNRESOLVED REFERENCES ===")

    counts = {}

    for decision in unresolved:
        key = (
            decision["organisation_name"],
            decision["relationship_type"],
        )

        counts[key] = counts.get(key, 0) + 1

    for (name, relationship), count in sorted(
        counts.items(),
        key=lambda x: (-x[1], x[0][0])
    ):

        print(
            f"{count:>4} | "
            f"{relationship:<12} | "
            f"{name}"
        )

    print()
    print("=== AMBIGUOUS REFERENCES ===")

    for decision in ambiguous:
        print(
            f"{decision['relationship_type']:<12} | "
            f"{decision['organisation_name']}"
        )


def main():
    db = "data/iati_intelligence.db"

    conn = sqlite3.connect(db)

    try:
        decisions = resolve_opportunity_references(conn)
        print_audit(decisions)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
