#!/usr/bin/env python3
"""Recreate approved semantic duplicate relationships using live entity IDs.

This script intentionally resolves relationships by canonical names at run
time.  It never carries legacy ``ORG-*`` identifiers forward into the current
03D registry.
"""

import sqlite3
import uuid

from organisation_resolution.normalizer import normalize_name

DB = "data/iati_intelligence.db"

# Canonical-name pairs approved by the manual entity audit.  The first name is
# the canonical parent; the second is the duplicate/alias child.
PAIRS = [
    ("British Council", "The British Council"),
    ("Pandemic Fund", "The Pandemic Fund"),
    ("University of Manchester", "The University of Manchester"),
    ("University of Oxford", "The University of Oxford"),
    (
        "William and Flora Hewlett Foundation",
        "The William and Flora Hewlett Foundation",
    ),
    ("World Bank - Washington D.C.", "World Bank"),
]


def candidate_names(name):
    normalized = normalize_name(name)
    candidates = [normalized]
    if normalized.startswith("the "):
        candidates.append(normalized[4:])
    else:
        candidates.append(f"the {normalized}")
    return list(dict.fromkeys(candidates))


def find_entities(conn, name):
    """Return all ACTIVE entities matching a canonical name candidate."""
    matches = []
    for candidate in candidate_names(name):
        rows = conn.execute(
            """
            SELECT entity_id, canonical_name, entity_status
            FROM organisation_entities
            WHERE canonical_name = ?
              AND entity_status = 'ACTIVE'
            """,
            (candidate,),
        ).fetchall()
        matches.extend(rows)
    return {row[0]: row for row in matches}


def find_entity(conn, name):
    """Return the unique ACTIVE entity matching a canonical name.

    Ambiguous names are deliberately unresolved.  The 03D guardrail is that
    we must never invent a relationship when more than one active entity
    matches the approved semantic name.
    """
    by_id = find_entities(conn, name)
    if len(by_id) == 1:
        return next(iter(by_id))
    return None


def remove_stale_relationships(conn):
    """Remove only DUPLICATE_OF rows whose endpoints are no longer live."""
    conn.execute(
        """
        DELETE FROM organisation_relationships
        WHERE relationship_type = 'DUPLICATE_OF'
          AND (
              parent_entity_id NOT IN (
                  SELECT entity_id FROM organisation_entities
              )
              OR child_entity_id NOT IN (
                  SELECT entity_id FROM organisation_entities
              )
          )
        """
    )


def main():
    conn = sqlite3.connect(DB)
    try:
        conn.execute("BEGIN")
        created = 0
        skipped = 0

        remove_stale_relationships(conn)

        for canonical_name, duplicate_name in PAIRS:
            parent_matches = find_entities(conn, canonical_name)
            child_matches = find_entities(conn, duplicate_name)

            if len(parent_matches) != 1 or len(child_matches) != 1:
                skipped += 1
                parent_detail = sorted(parent_matches)
                child_detail = sorted(child_matches)
                print(
                    f"SKIP    {canonical_name!r} <- {duplicate_name!r} "
                    f"(ambiguous/absent current entities; "
                    f"parent={parent_detail}, child={child_detail})"
                )
                continue

            parent_id = next(iter(parent_matches))
            child_id = next(iter(child_matches))

            if parent_id == child_id:
                skipped += 1
                print(
                    f"SKIP    {canonical_name!r} <- {duplicate_name!r} "
                    "(pair resolved to the same current entity)"
                )
                continue

            exists = conn.execute(
                """
                SELECT relationship_id
                FROM organisation_relationships
                WHERE parent_entity_id = ?
                  AND child_entity_id = ?
                  AND relationship_type = 'DUPLICATE_OF'
                """,
                (parent_id, child_id),
            ).fetchone()

            if exists:
                print(f"EXISTS  {parent_id} <- {child_id}")
                continue

            conn.execute(
                """
                INSERT INTO organisation_relationships (
                    relationship_id,
                    parent_entity_id,
                    child_entity_id,
                    relationship_type,
                    source_system,
                    confidence_score
                )
                VALUES (?, ?, ?, 'DUPLICATE_OF', 'MANUAL_AUDIT', 1.0)
                """,
                (str(uuid.uuid4()), parent_id, child_id),
            )
            created += 1
            print(f"ADDED   {parent_id} <- {child_id}")

        conn.commit()
        print(
            f"Semantic relationships ready: {created} created, "
            f"{skipped} approved pairs skipped because current entities were "
            "ambiguous or absent."
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
