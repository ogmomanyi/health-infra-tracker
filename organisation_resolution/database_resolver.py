"""
Database-backed Organisation Entity Resolution.

Loads canonical entities and aliases from SQLite and resolves
source organisation records using the existing resolution engine.

This module does not modify the database. It only performs
resolution and returns decisions.
"""

import sqlite3

from organisation_resolution.normalizer import normalize_name
from organisation_resolution.resolver import resolve_organisation


DB_PATH = "data/iati_intelligence.db"


def load_entity_candidates(conn):
    """
    Load canonical organisation entities as matcher candidates.
    """

    rows = conn.execute(
        """
        SELECT
            entity_id,
            canonical_name
        FROM organisation_entities
        WHERE entity_status = 'ACTIVE'
        ORDER BY entity_id
        """
    ).fetchall()

    return [
        {
            "entity_id": entity_id,
            "canonical_name": canonical_name,
            "normalized_name": normalize_name(canonical_name),
        }
        for entity_id, canonical_name in rows
    ]


def load_alias_candidates(conn):
    """
    Load unambiguous aliases as matcher candidates.

    An alias is considered safe for automatic matching only when
    its normalized form maps to exactly one entity.
    """

    rows = conn.execute(
        """
        SELECT
             a.alias_name,
             a.entity_id
        FROM organisation_aliases a
        JOIN organisation_entities e
             ON e.entity_id = a.entity_id
        WHERE e.entity_status = 'ACTIVE'
        ORDER BY a.alias_id
        """
    ).fetchall()

    alias_entities = {}

    for alias_name, entity_id in rows:
        normalized = normalize_name(alias_name)

        if not normalized:
            continue

        alias_entities.setdefault(
            normalized,
            set()
        ).add(entity_id)

    candidates = []

    for normalized_name, entity_ids in alias_entities.items():

        if len(entity_ids) != 1:
            continue

        entity_id = next(iter(entity_ids))

        candidates.append(
            {
                "entity_id": entity_id,
                "canonical_name": normalized_name,
                "normalized_name": normalized_name,
            }
        )

    return candidates


def load_candidates(conn):
    """
    Load canonical names and safe aliases.

    Canonical entities are always included.

    Only aliases that unambiguously belong to one entity
    are included.
    """

    canonical_candidates = load_entity_candidates(conn)
    alias_candidates = load_alias_candidates(conn)

    candidates = canonical_candidates.copy()

    existing = {
        (
            candidate["entity_id"],
            candidate["normalized_name"],
        )
        for candidate in candidates
    }

    for candidate in alias_candidates:

        key = (
            candidate["entity_id"],
            candidate["normalized_name"],
        )

        if key not in existing:
            candidates.append(candidate)

    return candidates

def get_canonical_entity_id(conn, entity_id):
    """
    Follow DUPLICATE_OF relationships until the canonical entity is reached.

    Relationships are stored as:
        parent_entity_id = canonical entity
        child_entity_id  = duplicate entity

    Returns the original entity_id when no relationship exists.

    Raises RuntimeError if a relationship cycle is detected.
    """

    current_id = entity_id
    visited = set()

    while True:
        if current_id in visited:
            raise RuntimeError(
                f"Cycle detected in organisation relationships at {current_id}"
            )

        visited.add(current_id)

        row = conn.execute(
            """
            SELECT parent_entity_id
            FROM organisation_relationships
            WHERE child_entity_id = ?
              AND relationship_type = 'DUPLICATE_OF'
            """,
            (current_id,),
        ).fetchone()

        if row is None:
            return current_id

        current_id = row[0]    


def resolve_source_record(
    conn,
    organisation_record,
    candidates=None,
):
    """
    Resolve one organisation_intelligence record.

    Known placeholder names are classified as NON_ENTITY
    and are never matched to organisation_entities.
    """

    organisation_name = organisation_record.get("org_name")

    if is_non_entity_name(organisation_name):
        return {
            "organisation_key":
                organisation_record.get(
                    "organisation_key"
                ),

            "org_ref":
                organisation_record.get(
                    "org_ref"
                ),

            "alias_name":
                organisation_name,

            "normalized_name":
                normalize_name(
                    organisation_name
                ),

            "entity_id":
                None,

            "match_method":
                "NON_ENTITY",

            "confidence_score":
                0.0,

            "resolution_action":
                "EXCLUDED",
        }

    if candidates is None:
        candidates = load_candidates(conn)

    result = resolve_organisation(
      organisation_record,
      candidates,
    )

    if result.get("entity_id"):
       result["entity_id"] = get_canonical_entity_id(
       conn,
       result["entity_id"],
      )

    return result

def load_unresolved_source_records(conn):
    """
    Return source records that do not currently have an alias.
    """

    return conn.execute(
        """
        SELECT
            oi.organisation_key,
            oi.org_ref,
            oi.org_name
        FROM organisation_intelligence oi
        LEFT JOIN organisation_aliases oa
            ON oi.organisation_key = oa.organisation_key
        WHERE oa.organisation_key IS NULL
          AND oi.org_name IS NOT NULL
        ORDER BY oi.org_name
        """
    ).fetchall()


def resolve_unresolved_records(conn):
    """
    Resolve all currently unresolved source records.

    Returns:
        {
            "matched": [...],
            "unresolved": [...]
        }
    """

    candidates = load_candidates(conn)

    rows = load_unresolved_source_records(conn)

    matched = []
    unresolved = []
    excluded = []

    for organisation_key, org_ref, org_name in rows:

        record = {
            "organisation_key": organisation_key,
            "org_ref": org_ref,
            "org_name": org_name,
        }

        result = resolve_source_record(
            conn,
            record,
            candidates,
        )

        if result["resolution_action"] == "MATCHED":
         matched.append(result)

        elif result["resolution_action"] == "EXCLUDED":
         excluded.append(result)

        else:
         unresolved.append(result)

    return {
    "matched": matched,
    "unresolved": unresolved,
    "excluded": excluded,
}


NON_ENTITY_NAMES = {
    "anonymous",
    "ip not published",
    "undefined",
}


def is_non_entity_name(name):
    """
    Return True when an organisation name is a known
    placeholder rather than a real organisation.
    """

    return normalize_name(name) in NON_ENTITY_NAMES


def inspect_resolution():
    """
    Diagnostic entry point.

    Does not modify the database.
    """

    conn = sqlite3.connect(DB_PATH)

    try:
        results = resolve_unresolved_records(conn)

        print(
            f"Unresolved source records: "
            f"{len(results['matched']) + len(results['unresolved'])}"
        )

        print(
            f"Matched: "
            f"{len(results['matched'])}"
        )

        print(
            f"Still unresolved: "
            f"{len(results['unresolved'])}"
        )

    finally:
        conn.close()


if __name__ == "__main__":
    inspect_resolution()
    