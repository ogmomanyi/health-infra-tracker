#!/usr/bin/env python3
"""Migrate legacy organisation references into the canonical 03D model.

The 03D repair introduced stable ``org_*`` entity IDs while older semantic
and group tables may still contain ``ORG-*`` IDs.  This migration maps those
legacy IDs by canonical name and rewrites dependent references, including
semantic relationships.  Legacy relationship rows are preserved for audit.

The migration is idempotent and refuses to silently leave a known legacy
reference in a current table.
"""

import sqlite3

from organisation_resolution.normalizer import normalize_name

DB = "data/iati_intelligence.db"
LEGACY_ENTITIES = "organisation_entities_intelligence_legacy"


def table_exists(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def build_legacy_map(conn):
    """Map every legacy entity ID to the current entity with the same name."""
    if not table_exists(conn, LEGACY_ENTITIES):
        return {}

    canonical = {}
    for entity_id, name in conn.execute(
        "SELECT entity_id, canonical_name FROM organisation_entities"
    ):
        key = normalize_name(name)
        if key:
            canonical.setdefault(key, set()).add(entity_id)

    mapping = {}
    for legacy_id, name in conn.execute(
        f"SELECT organisation_entity_id, canonical_name FROM {LEGACY_ENTITIES}"
    ):
        key = normalize_name(name)
        candidates = canonical.get(key, set())
        if len(candidates) == 1:
            mapping[legacy_id] = next(iter(candidates))

    return mapping


def migrate_entity_column(conn, table, column, mapping):
    if not table_exists(conn, table):
        return 0

    changed = 0
    rows = conn.execute(
        f'SELECT rowid, "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL'
    ).fetchall()

    for rowid, old_id in rows:
        new_id = mapping.get(old_id)
        if not new_id or new_id == old_id:
            continue
        conn.execute(
            f'UPDATE "{table}" SET "{column}"=? WHERE rowid=?',
            (new_id, rowid),
        )
        changed += 1

    return changed


def migrate_group_members(conn, mapping):
    table = "organisation_group_members"
    if not table_exists(conn, table):
        return 0

    changed = 0
    rows = conn.execute(
        "SELECT group_id, entity_id FROM organisation_group_members"
    ).fetchall()

    for group_id, old_id in rows:
        new_id = mapping.get(old_id)
        if not new_id or new_id == old_id:
            continue

        collision = conn.execute(
            "SELECT 1 FROM organisation_group_members WHERE group_id=? AND entity_id=?",
            (group_id, new_id),
        ).fetchone()

        if collision:
            conn.execute(
                "DELETE FROM organisation_group_members WHERE group_id=? AND entity_id=?",
                (group_id, old_id),
            )
        else:
            conn.execute(
                "UPDATE organisation_group_members SET entity_id=? WHERE group_id=? AND entity_id=?",
                (new_id, group_id, old_id),
            )
        changed += 1

    return changed


def rebuild_relationships(conn, mapping):
    """Rewrite current/legacy relationship rows using canonical IDs."""
    if not table_exists(conn, "organisation_relationships"):
        return 0

    rows = conn.execute(
        """
        SELECT relationship_id, parent_entity_id, child_entity_id,
               relationship_type, source_system, confidence_score, created_at
        FROM organisation_relationships
        """
    ).fetchall()

    if table_exists(conn, "organisation_relationships_legacy"):
        rows += conn.execute(
            """
            SELECT relationship_id, parent_entity_id, child_entity_id,
                   relationship_type, source_system, confidence_score, created_at
            FROM organisation_relationships_legacy
            """
        ).fetchall()

    conn.execute("DROP TABLE IF EXISTS organisation_relationships_03d_backup")
    conn.execute("ALTER TABLE organisation_relationships RENAME TO organisation_relationships_03d_backup")

    conn.execute(
        """
        CREATE TABLE organisation_relationships (
            relationship_id TEXT PRIMARY KEY,
            parent_entity_id TEXT NOT NULL,
            child_entity_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL,
            source_system TEXT NOT NULL DEFAULT 'IATI',
            confidence_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (parent_entity_id) REFERENCES organisation_entities(entity_id),
            FOREIGN KEY (child_entity_id) REFERENCES organisation_entities(entity_id)
        )
        """
    )

    inserted = 0
    seen = set()
    for relationship_id, parent, child, rel_type, source, confidence, created_at in rows:
        parent = mapping.get(parent, parent)
        child = mapping.get(child, child)

        if not parent or not child:
            continue

        parent_exists = conn.execute(
            "SELECT 1 FROM organisation_entities WHERE entity_id=?",
            (parent,),
        ).fetchone()
        child_exists = conn.execute(
            "SELECT 1 FROM organisation_entities WHERE entity_id=?",
            (child,),
        ).fetchone()
        if not parent_exists or not child_exists:
            continue

        logical_key = (parent, child, rel_type, source, confidence)
        if logical_key in seen:
            continue
        seen.add(logical_key)

        conn.execute(
            """
            INSERT INTO organisation_relationships
            (relationship_id, parent_entity_id, child_entity_id,
             relationship_type, source_system, confidence_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (relationship_id, parent, child, rel_type, source, confidence, created_at),
        )
        inserted += 1

    return inserted


def validate_no_legacy_references(conn):
    checks = {}

    for table, columns in {
        "organisation_relationships": ["parent_entity_id", "child_entity_id"],
        "organisation_group_members": ["entity_id"],
        "organisation_resolution_log": ["entity_id"],
        "organisation_manual_overrides": ["entity_id"],
        "opportunity_organisation_resolution": ["entity_id"],
    }.items():
        if not table_exists(conn, table):
            continue
        for column in columns:
            count = conn.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" LIKE \'ORG-%\''
            ).fetchone()[0]
            checks[f"{table}.{column}"] = count

    failures = {key: value for key, value in checks.items() if value}
    if failures:
        raise RuntimeError(f"Legacy ORG-* references remain: {failures}")


def main():
    conn = sqlite3.connect(DB)
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN")

        mapping = build_legacy_map(conn)
        print(f"Legacy entity mappings available: {len(mapping)}")

        migrated = {}
        for table in (
            "opportunity_organisation_resolution",
            "organisation_resolution_log",
            "organisation_manual_overrides",
        ):
            migrated[table] = migrate_entity_column(conn, table, "entity_id", mapping)

        migrated["organisation_group_members"] = migrate_group_members(conn, mapping)
        migrated["organisation_relationships"] = rebuild_relationships(conn, mapping)

        validate_no_legacy_references(conn)
        conn.commit()

        for table, count in migrated.items():
            print(f"{table}: migrated/rebuilt {count} references")
        print("03D entity-reference migration PASSED")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
