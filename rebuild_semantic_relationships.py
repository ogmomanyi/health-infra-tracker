#!/usr/bin/env python3
"""Recreate approved semantic duplicate relationships using live entity IDs."""

import sqlite3
import uuid

from organisation_resolution.normalizer import normalize_name

DB = "data/iati_intelligence.db"

PAIRS = [
    ("British Council", "The British Council"),
    (
        "Malawi Liverpool Wellcome Trust Clinical Research Programme",
        "The Malawi Liverpool Wellcome Trust Clinical Research Programme",
    ),
    ("Pandemic Fund", "The Pandemic Fund"),
    ("University of Manchester", "The University of Manchester"),
    ("University of Oxford", "The University of Oxford"),
    (
        "William and Flora Hewlett Foundation",
        "The William and Flora Hewlett Foundation",
    ),
    ("World Bank", "The World Bank"),
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
    for candidate in candidate_names(name):
        row = conn.execute(
            """
            SELECT entity_id, canonical_name, entity_status
            FROM organisation_entities
            WHERE canonical_name = ?
            """,
            (candidate,),
        ).fetchone()
        if row is not None:
            if row[2] != "ACTIVE":
                raise RuntimeError(f"Entity is not ACTIVE: {row}")
            return row[0]

    raise RuntimeError(
        f"Canonical entity not found for {name!r}; tried {candidate_names(name)!r}"
    )


def main():
    conn = sqlite3.connect(DB)
    try:
        conn.execute("BEGIN")
        created = 0

        for canonical_name, duplicate_name in PAIRS:
            parent_id = find_entity(conn, canonical_name)
            child_id = find_entity(conn, duplicate_name)

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
        print(f"Semantic relationships ready: {created} created.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
