#!/usr/bin/env python3
"""Repair the 03D organisation/entity schema mismatch.

The intelligence builder historically wrote its derived organisation dataframe
into ``organisation_entities``. That table is owned by entity resolution and
uses ``entity_id``. This migration preserves the derived table as a legacy
backup, recreates the canonical entity-resolution schema, and rebuilds the
canonical registry/aliases from the normalized organisations CSV.

Entity IDs deliberately use the same deterministic ``org_*`` namespace as the
current intelligence pipeline. This prevents the repair script from reintroducing
the retired ``ORG-*`` namespace.
"""

import csv
import hashlib
import sqlite3
from pathlib import Path

from organisation_resolution.normalizer import normalize_name

DB_PATH = Path("data/iati_intelligence.db")
ORGANISATIONS_CSV = Path("data/organisations.csv")


def table_columns(conn, table):
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def stable_entity_id(org_ref, canonical_name):
    """Return the deterministic ID used by the intelligence builder."""
    ref = " ".join(str(org_ref or "").split())
    if ref:
        key = f"ref:{ref.lower()}"
    else:
        key = f"name:{canonical_name.lower()}"

    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"org_{digest}"


def clean(value):
    return " ".join(str(value or "").split())


def ensure_schema(conn):
    conn.execute("PRAGMA foreign_keys=OFF")

    if table_exists(conn, "organisation_entities"):
        columns = set(table_columns(conn, "organisation_entities"))
        if "entity_id" not in columns:
            backup = "organisation_entities_intelligence_legacy"
            if table_exists(conn, backup):
                conn.execute(f"DROP TABLE {backup}")
            conn.execute(f"ALTER TABLE organisation_entities RENAME TO {backup}")

    if table_exists(conn, "organisation_aliases"):
        columns = set(table_columns(conn, "organisation_aliases"))
        if "entity_id" not in columns or "alias_id" not in columns:
            backup = "organisation_aliases_intelligence_legacy"
            if table_exists(conn, backup):
                conn.execute(f"DROP TABLE {backup}")
            conn.execute(f"ALTER TABLE organisation_aliases RENAME TO {backup}")

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS organisation_entities (
            entity_id TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL UNIQUE,
            organisation_type TEXT,
            entity_status TEXT DEFAULT 'ACTIVE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_org_type ON organisation_entities(organisation_type);
        CREATE INDEX IF NOT EXISTS idx_org_status ON organisation_entities(entity_status);

        CREATE TABLE IF NOT EXISTS organisation_aliases (
            alias_id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL,
            organisation_key TEXT NOT NULL,
            org_ref TEXT,
            alias_name TEXT NOT NULL,
            source_system TEXT NOT NULL DEFAULT 'IATI',
            is_primary_alias INTEGER DEFAULT 0,
            match_method TEXT NOT NULL,
            confidence_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (entity_id) REFERENCES organisation_entities(entity_id)
        );

        CREATE INDEX IF NOT EXISTS idx_alias_entity ON organisation_aliases(entity_id);
        CREATE INDEX IF NOT EXISTS idx_alias_org_key ON organisation_aliases(organisation_key);
        CREATE INDEX IF NOT EXISTS idx_alias_org_ref ON organisation_aliases(org_ref);
        CREATE INDEX IF NOT EXISTS idx_alias_name ON organisation_aliases(alias_name);

        CREATE TABLE IF NOT EXISTS organisation_relationships (
            relationship_id TEXT PRIMARY KEY,
            parent_entity_id TEXT NOT NULL,
            child_entity_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL,
            source_system TEXT NOT NULL DEFAULT 'IATI',
            confidence_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (parent_entity_id) REFERENCES organisation_entities(entity_id),
            FOREIGN KEY (child_entity_id) REFERENCES organisation_entities(entity_id)
        );
        """
    )


def load_organisations():
    if not ORGANISATIONS_CSV.exists():
        raise FileNotFoundError(f"Missing normalized source: {ORGANISATIONS_CSV}")

    with ORGANISATIONS_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def rebuild_entities(conn, rows):
    entities = {}
    aliases = {}

    for row in rows:
        org_ref = clean(row.get("org_ref"))
        org_name = clean(row.get("org_name"))
        role = clean(row.get("role"))
        org_type = clean(row.get("org_type"))
        activity_id = clean(row.get("activity_id"))

        if not org_ref and not org_name:
            continue

        raw_name = org_name or org_ref
        canonical = normalize_name(raw_name)
        if not canonical:
            continue

        entity_id = stable_entity_id(org_ref, canonical)
        organisation_key = f"ref:{org_ref.lower()}" if org_ref else f"name:{canonical}"

        existing = entities.get(entity_id)
        if existing is None:
            entities[entity_id] = {
                "canonical_name": canonical,
                "organisation_type": org_type,
            }
        elif not existing["organisation_type"] and org_type:
            existing["organisation_type"] = org_type

        alias_key = (entity_id, organisation_key, org_ref, raw_name, role, activity_id)
        aliases[alias_key] = {
            "entity_id": entity_id,
            "organisation_key": organisation_key,
            "org_ref": org_ref,
            "alias_name": raw_name,
        }

    for entity_id, entity in entities.items():
        conn.execute(
            """
            INSERT OR IGNORE INTO organisation_entities
                (entity_id, canonical_name, organisation_type, entity_status)
            VALUES (?, ?, ?, 'ACTIVE')
            """,
            (entity_id, entity["canonical_name"], entity["organisation_type"]),
        )

    for alias_key, alias in aliases.items():
        alias_id = hashlib.sha1("|".join(map(str, alias_key)).encode("utf-8")).hexdigest()
        conn.execute(
            """
            INSERT OR IGNORE INTO organisation_aliases
                (alias_id, entity_id, organisation_key, org_ref, alias_name,
                 source_system, is_primary_alias, match_method, confidence_score)
            VALUES (?, ?, ?, ?, ?, 'IATI', 1, 'REBUILD_FROM_NORMALIZED', 1.0)
            """,
            (
                alias_id,
                alias["entity_id"],
                alias["organisation_key"],
                alias["org_ref"],
                alias["alias_name"],
            ),
        )

    return len(entities), len(aliases)


def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(DB_PATH)

    rows = load_organisations()
    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_schema(conn)
        entities, aliases = rebuild_entities(conn, rows)

        orphan_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM organisation_relationships r
            WHERE NOT EXISTS (SELECT 1 FROM organisation_entities e WHERE e.entity_id = r.parent_entity_id)
               OR NOT EXISTS (SELECT 1 FROM organisation_entities e WHERE e.entity_id = r.child_entity_id)
            """
        ).fetchone()[0]

        if orphan_count:
            if table_exists(conn, "organisation_relationships_legacy"):
                conn.execute("DROP TABLE organisation_relationships_legacy")
            conn.execute("ALTER TABLE organisation_relationships RENAME TO organisation_relationships_legacy")
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

        conn.commit()
        print(f"Rebuilt canonical entities: {entities}")
        print(f"Rebuilt aliases: {aliases}")
        print(f"Orphaned legacy relationships preserved: {orphan_count}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
