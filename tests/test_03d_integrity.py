import sqlite3

from organisation_resolution.database_resolver import get_canonical_entity_id


def make_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE organisation_entities (
            entity_id TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL UNIQUE,
            organisation_type TEXT,
            entity_status TEXT DEFAULT 'ACTIVE'
        );

        CREATE TABLE organisation_aliases (
            alias_id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL,
            organisation_key TEXT NOT NULL,
            org_ref TEXT,
            alias_name TEXT NOT NULL,
            source_system TEXT NOT NULL DEFAULT 'IATI',
            is_primary_alias INTEGER DEFAULT 0,
            match_method TEXT NOT NULL,
            confidence_score REAL
        );

        CREATE TABLE organisation_relationships (
            relationship_id TEXT PRIMARY KEY,
            parent_entity_id TEXT NOT NULL,
            child_entity_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL,
            source_system TEXT NOT NULL DEFAULT 'IATI',
            confidence_score REAL
        );
        """
    )
    return conn


def test_canonical_namespace_is_org_prefix():
    conn = make_db()
    conn.execute(
        "INSERT INTO organisation_entities(entity_id, canonical_name) VALUES (?, ?)",
        ("org_canonical", "british council"),
    )
    entity_id = conn.execute("SELECT entity_id FROM organisation_entities").fetchone()[0]
    assert entity_id.startswith("org_")
    conn.close()


def test_duplicate_resolution_follows_current_relationship():
    conn = make_db()
    conn.executemany(
        "INSERT INTO organisation_entities(entity_id, canonical_name) VALUES (?, ?)",
        [
            ("org_parent", "british council"),
            ("org_child", "the british council"),
        ],
    )
    conn.execute(
        """
        INSERT INTO organisation_relationships
        (relationship_id, parent_entity_id, child_entity_id, relationship_type)
        VALUES ('rel-1', 'org_parent', 'org_child', 'DUPLICATE_OF')
        """
    )

    assert get_canonical_entity_id(conn, "org_child") == "org_parent"
    assert get_canonical_entity_id(conn, "org_parent") == "org_parent"
    conn.close()


def test_legacy_namespace_is_not_a_valid_current_entity():
    conn = make_db()
    conn.execute(
        "INSERT INTO organisation_entities(entity_id, canonical_name) VALUES (?, ?)",
        ("org_current", "world bank"),
    )
    current = {
        row[0]
        for row in conn.execute("SELECT entity_id FROM organisation_entities")
    }
    assert all(not entity_id.startswith("ORG-") for entity_id in current)
    conn.close()
