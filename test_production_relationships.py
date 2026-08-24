import sqlite3
from pathlib import Path

from organisation_resolution.database_resolver import get_canonical_entity_id


DB_PATH = Path("data/iati_intelligence.db")


def entity_id_column(conn):
    columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(organisation_entities)")
    }

    if "entity_id" in columns:
        return "entity_id"

    return "organisation_entity_id"


def duplicate_relationships(conn):
    id_column = entity_id_column(conn)

    return conn.execute(
        f"""
        SELECT
            r.parent_entity_id,
            p.canonical_name,
            r.child_entity_id,
            c.canonical_name
        FROM organisation_relationships r
        JOIN organisation_entities p
            ON p.{id_column} = r.parent_entity_id
        JOIN organisation_entities c
            ON c.{id_column} = r.child_entity_id
        WHERE r.relationship_type = 'DUPLICATE_OF'
        ORDER BY p.canonical_name
        """
    ).fetchall()


def relationship_failures(conn):
    failures = []

    for parent_id, parent_name, child_id, child_name in duplicate_relationships(conn):
        resolved_parent = get_canonical_entity_id(conn, parent_id)
        resolved_child = get_canonical_entity_id(conn, child_id)

        if resolved_parent != parent_id or resolved_child != parent_id:
            failures.append(
                {
                    "parent_id": parent_id,
                    "parent_name": parent_name,
                    "child_id": child_id,
                    "child_name": child_name,
                    "resolved_parent": resolved_parent,
                    "resolved_child": resolved_child,
                }
            )

    return failures


def test_duplicate_relationships_resolve_to_canonical_parent():
    conn = sqlite3.connect(DB_PATH)

    try:
        assert relationship_failures(conn) == []
    finally:
        conn.close()


def main():
    conn = sqlite3.connect(DB_PATH)

    try:
        relationships = duplicate_relationships(conn)
        failures = relationship_failures(conn)

        print("=== PRODUCTION RELATIONSHIP CHECK ===")
        print(f"Relationships found: {len(relationships)}")

        if failures:
            print("=== FAILURES ===")
            for failure in failures:
                print(failure)
            raise SystemExit(1)

        print("All DUPLICATE_OF relationships resolve to their canonical parent.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
