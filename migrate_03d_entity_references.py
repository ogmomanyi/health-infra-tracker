#!/usr/bin/env python3
"""Safely migrate legacy organisation references into the canonical 03D model.

The 03D repair introduced stable ``org_*`` entity IDs while older semantic,
group, and opportunity tables may still contain ``ORG-*`` IDs.  This migration
rewrites those references only when the legacy ID can be mapped unambiguously
to one active canonical entity.

Relationship evidence is never silently discarded.  Every source relationship
is classified as MIGRATED, DUPLICATE, or UNRESOLVED in an audit table.  Any
unresolved relationship aborts the transaction so a partially migrated database
cannot be committed.
"""

import hashlib
import sqlite3

from organisation_resolution.normalizer import normalize_name

DB = "data/iati_intelligence.db"
LEGACY_ENTITIES = "organisation_entities_intelligence_legacy"
AUDIT_TABLE = "organisation_relationship_migration_audit"


def table_exists(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def columns(conn, table):
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def build_legacy_map(conn):
    """Map legacy entity IDs to exactly one active canonical entity.

    A legacy name that maps to zero or multiple active canonical entities is
    deliberately left unresolved; guessing here would corrupt identity data.
    """
    if not table_exists(conn, LEGACY_ENTITIES):
        return {}, {}

    canonical = {}
    for entity_id, name, status in conn.execute(
        "SELECT entity_id, canonical_name, entity_status FROM organisation_entities"
    ):
        if status not in (None, "ACTIVE"):
            continue
        key = normalize_name(name)
        if key:
            canonical.setdefault(key, set()).add(entity_id)

    mapping = {}
    unresolved = {}
    for legacy_id, name in conn.execute(
        f"SELECT organisation_entity_id, canonical_name FROM {LEGACY_ENTITIES}"
    ):
        key = normalize_name(name)
        candidates = canonical.get(key, set())
        if len(candidates) == 1:
            mapping[legacy_id] = next(iter(candidates))
        else:
            unresolved[legacy_id] = sorted(candidates)

    return mapping, unresolved


def migrate_entity_column(conn, table, column, mapping):
    if not table_exists(conn, table) or column not in columns(conn, table):
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
    rows = conn.execute("SELECT group_id, entity_id FROM organisation_group_members").fetchall()
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


def ensure_audit_table(conn):
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {AUDIT_TABLE} (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            relationship_id TEXT NOT NULL,
            parent_entity_id TEXT NOT NULL,
            child_entity_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL,
            source_system TEXT,
            confidence_score REAL,
            created_at TIMESTAMP,
            mapped_parent_entity_id TEXT,
            mapped_child_entity_id TEXT,
            action TEXT NOT NULL,
            reason TEXT,
            audited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def deterministic_relationship_id(original_id, parent, child, rel_type, source, confidence):
    payload = "|".join(
        [str(original_id), parent, child, rel_type, str(source), str(confidence)]
    )
    return "rel-03d-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def rebuild_relationships(conn, mapping):
    """Rebuild relationships without silently dropping any source row."""
    if not table_exists(conn, "organisation_relationships"):
        return {"migrated": 0, "duplicates": 0, "unresolved": 0}

    ensure_audit_table(conn)

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

    # The old table remains available as source evidence.  The new table is
    # constructed from the complete source set inside the same transaction.
    conn.execute("DROP TABLE IF EXISTS organisation_relationships_03d_backup")
    conn.execute(
        "ALTER TABLE organisation_relationships RENAME TO organisation_relationships_03d_backup"
    )
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

    seen = set()
    used_ids = set()
    stats = {"migrated": 0, "duplicates": 0, "unresolved": 0}
    for relationship_id, parent, child, rel_type, source, confidence, created_at in rows:
        mapped_parent = mapping.get(parent, parent)
        mapped_child = mapping.get(child, child)
        parent_exists = conn.execute(
            "SELECT 1 FROM organisation_entities WHERE entity_id=?",
            (mapped_parent,),
        ).fetchone()
        child_exists = conn.execute(
            "SELECT 1 FROM organisation_entities WHERE entity_id=?",
            (mapped_child,),
        ).fetchone()

        if not parent_exists or not child_exists:
            stats["unresolved"] += 1
            conn.execute(
                f"""
                INSERT INTO {AUDIT_TABLE}
                (relationship_id, parent_entity_id, child_entity_id,
                 relationship_type, source_system, confidence_score, created_at,
                 mapped_parent_entity_id, mapped_child_entity_id, action, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'UNRESOLVED', ?)
                """,
                (
                    relationship_id, parent, child, rel_type, source, confidence, created_at,
                    mapped_parent, mapped_child,
                    "relationship endpoint does not resolve to an active canonical entity",
                ),
            )
            continue

        logical_key = (mapped_parent, mapped_child, rel_type, source, confidence)
        if logical_key in seen:
            stats["duplicates"] += 1
            conn.execute(
                f"""
                INSERT INTO {AUDIT_TABLE}
                (relationship_id, parent_entity_id, child_entity_id,
                 relationship_type, source_system, confidence_score, created_at,
                 mapped_parent_entity_id, mapped_child_entity_id, action, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'DUPLICATE', ?)
                """,
                (
                    relationship_id, parent, child, rel_type, source, confidence, created_at,
                    mapped_parent, mapped_child, "duplicate logical relationship",
                ),
            )
            continue

        seen.add(logical_key)
        new_id = relationship_id
        if new_id in used_ids:
            new_id = deterministic_relationship_id(
                relationship_id, mapped_parent, mapped_child, rel_type, source, confidence
            )
        used_ids.add(new_id)

        conn.execute(
            """
            INSERT INTO organisation_relationships
            (relationship_id, parent_entity_id, child_entity_id,
             relationship_type, source_system, confidence_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (new_id, mapped_parent, mapped_child, rel_type, source, confidence, created_at),
        )
        conn.execute(
            f"""
            INSERT INTO {AUDIT_TABLE}
            (relationship_id, parent_entity_id, child_entity_id,
             relationship_type, source_system, confidence_score, created_at,
             mapped_parent_entity_id, mapped_child_entity_id, action, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'MIGRATED', ?)
            """,
            (
                relationship_id, parent, child, rel_type, source, confidence, created_at,
                mapped_parent, mapped_child,
                "legacy/current relationship rewritten into canonical namespace",
            ),
        )
        stats["migrated"] += 1

    if stats["unresolved"]:
        raise RuntimeError(
            f"Refusing to commit migration: {stats['unresolved']} relationship(s) "
            "have unresolved canonical endpoints."
        )
    return stats


def validate_no_legacy_references(conn):
    checks = {}
    reference_columns = {
        "organisation_relationships": ["parent_entity_id", "child_entity_id"],
        "organisation_group_members": ["entity_id"],
        "organisation_resolution_log": ["entity_id"],
        "organisation_manual_overrides": ["entity_id"],
        "opportunity_organisation_resolution": ["entity_id"],
    }
    for table, table_columns in reference_columns.items():
        if not table_exists(conn, table):
            continue
        for column in table_columns:
            if column not in columns(conn, table):
                continue
            checks[f"{table}.{column}"] = conn.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" LIKE \'ORG-%\''
            ).fetchone()[0]

    failures = {key: value for key, value in checks.items() if value}
    if failures:
        raise RuntimeError(f"Legacy ORG-* references remain: {failures}")


def main():
    conn = sqlite3.connect(DB)
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN")

        mapping, ambiguous = build_legacy_map(conn)
        if ambiguous:
            raise RuntimeError(
                "Ambiguous legacy entity mappings; refusing to guess: "
                + repr(ambiguous)
            )
        print(f"Legacy entity mappings available: {len(mapping)}")

        migrated = {}
        for table in (
            "organisation_intelligence",
            "target_accounts",
            "recommended_actions",
            "programme_intelligence",
            "donor_intelligence",
            "equipment_entities",
            "opportunity_organisation_resolution",
            "organisation_resolution_log",
            "organisation_manual_overrides",
        ):
            migrated[table] = migrate_entity_column(conn, table, "organisation_entity_id", mapping)
            migrated[f"{table}.entity_id"] = migrate_entity_column(conn, table, "entity_id", mapping)

        migrated["organisation_group_members"] = migrate_group_members(conn, mapping)
        migrated["organisation_relationships"] = rebuild_relationships(conn, mapping)

        validate_no_legacy_references(conn)
        conn.commit()

        for table, result in migrated.items():
            print(f"{table}: {result}")
        print("03D entity-reference migration PASSED")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
