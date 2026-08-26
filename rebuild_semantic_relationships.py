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


def find_entity(conn, name):
    """Return the unique ACTIVE entity matching a canonical name."""
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

    # The same entity may be found through both candidate forms only when the
    # names are equivalent; de-duplicate by entity ID.
    by_id = {row[0]: row for row in matches}
    if len(by_id) == 1:
        return next(iter(by_id))
    if not by_id:
        return None

    raise RuntimeError(
        f"Ambiguous active entity for {name!r}: {sorted(by_id)}"
    )


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
            parent_id = find_entity(conn, canonical_name)
            child_id = find_entity(conn, duplicate_name)

            if parent_id is None or child_id is None:
                skipped += 1
                print(
                    f"SKIP    {canonical_name!r} <- {duplicate_name!r} "
                    f"(one or both current entities are absent)"
                )
                continue

            if parent_id == child_id:
                raise RuntimeError(
                    f"Semantic pair collapsed to one entity: {canonical_name!r}"
                )

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
            f"{skipped} approved pairs skipped because current entities are absent."
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
