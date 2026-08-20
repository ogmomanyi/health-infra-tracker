#!/usr/bin/env python3
"""Migrate dependent entity references after repairing the canonical registry.

The overwritten intelligence entity table used ``organisation_entity_id``.
The entity-resolution tables use ``entity_id``. The repair step preserves the
old intelligence table as ``organisation_entities_intelligence_legacy``;
this script maps dependent records from those legacy IDs to the new canonical
IDs using normalized organisation names.
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
    if not table_exists(conn, LEGACY_ENTITIES):
        return {}

    canonical = {
        normalize_name(name): entity_id
        for entity_id, name in conn.execute(
            "SELECT entity_id, canonical_name FROM organisation_entities"
        )
    }

    mapping = {}
    for legacy_id, name in conn.execute(
        f"SELECT organisation_entity_id, canonical_name FROM {LEGACY_ENTITIES}"
    ):
        new_id = canonical.get(normalize_name(name))
        if new_id:
            mapping[legacy_id] = new_id

    return mapping


def migrate_entity_column(conn, table, mapping):
    if not table_exists(conn, table):
        return 0

    changed = 0
    rows = conn.execute(
        f"SELECT rowid, entity_id FROM {table} WHERE entity_id IS NOT NULL"
    ).fetchall()

    for rowid, old_id in rows:
        new_id = mapping.get(old_id)
        if not new_id or new_id == old_id:
            continue
        conn.execute(
            f"UPDATE {table} SET entity_id=? WHERE rowid=?",
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
        "SELECT group_id, entity_id, membership_type, confidence_score, source_system FROM organisation_group_members"
    ).fetchall()

    for group_id, old_id, membership_type, confidence, source_system in rows:
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
                """
                UPDATE organisation_group_members
                SET entity_id=?
                WHERE group_id=? AND entity_id=?
                """,
                (new_id, group_id, old_id),
            )
        changed += 1

    return changed


def main():
    conn = sqlite3.connect(DB)
    try:
        conn.execute("BEGIN")
        mapping = build_legacy_map(conn)
        print(f"Legacy entity mappings available: {len(mapping)}")

        migrated = {}
        for table in (
            "opportunity_organisation_resolution",
            "organisation_resolution_log",
            "organisation_manual_overrides",
        ):
            migrated[table] = migrate_entity_column(conn, table, mapping)

        migrated["organisation_group_members"] = migrate_group_members(conn, mapping)

        conn.commit()
        for table, count in migrated.items():
            print(f"{table}: migrated {count} references")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
