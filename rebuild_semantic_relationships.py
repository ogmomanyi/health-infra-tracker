#!/usr/bin/env python3
"""Recreate the seven approved semantic duplicate relationships.

The previous relationship records used transient ORG-* IDs that belonged to
the overwritten intelligence-generated entity registry. After the canonical
registry is rebuilt, resolve the approved pairs by normalized canonical name
and create relationships against the live entity IDs.
"""

import sqlite3
import uuid

from organisation_resolution.normalizer import normalize_name

DB = "data/iati_intelligence.db"

PAIRS = [
    ("British Council", "The British Council", "Semantic duplicate"),
    (
        "Malawi Liverpool Wellcome Trust Clinical Research Programme",
        "The Malawi Liverpool Wellcome Trust Clinical Research Programme",
        "Semantic duplicate",
    ),
    ("Pandemic Fund", "The Pandemic Fund", "Semantic duplicate"),
    ("University of Manchester", "The University of Manchester", "Semantic duplicate"),
    ("University of Oxford", "The University of Oxford", "Semantic duplicate"),
    (
        "William and Flora Hewlett Foundation",
        "The William and Flora Hewlett Foundation",
        "Semantic duplicate",
    ),
    ("World Bank", "The World Bank", "Semantic duplicate"),
]


def find_entity(conn, name):
    normalized = normalize_name(name)
    row = conn.execute(
        """
        SELECT entity_id, canonical_name, entity_status
        FROM organisation_entities
        WHERE canonical_name = ?
        """,
        (normalized,),
    ).fetchone()

    if row is None:
        raise RuntimeError(
            f"Canonical entity not found for {name!r} (normalized={normalized!r})"
        )

    if row[2] != "ACTIVE":
        raise RuntimeError(f"Entity is not ACTIVE: {row}")

    return row[0]


def main():
    conn = sqlite3.connect(DB)

    try:
        conn.execute("BEGIN")
        created = 0

        for canonical_name, duplicate_name, reason in PAIRS:
            parent_id = find_entity(conn, canonical_name)
            child_id = find_entity(conn, duplicate_name)

            if parent_id == child_id:
                raise RuntimeError(
                    f"Semantic pair collapsed to the same entity: {canonical_name!r}"
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
            print(f"ADDED   {parent_id} <- {child_id}  ({reason})")

        conn.commit()
        print(f"Semantic relationships ready: {created} created.")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
