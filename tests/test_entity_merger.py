import sqlite3

import pytest

from organisation_resolution.entity_merger import merge_entities


def make_db():
    conn = sqlite3.connect(":memory:")

    conn.executescript(
        """
        CREATE TABLE organisation_entities (
            entity_id TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL UNIQUE,
            organisation_type TEXT,
            entity_status TEXT DEFAULT 'ACTIVE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            confidence_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE organisation_relationships (
            relationship_id TEXT PRIMARY KEY,
            parent_entity_id TEXT NOT NULL,
            child_entity_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL,
            source_system TEXT NOT NULL DEFAULT 'IATI',
            confidence_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    return conn


def seed(conn):
    conn.execute(
        """
        INSERT INTO organisation_entities
        (entity_id, canonical_name)
        VALUES
        ('TARGET', 'british council'),
        ('SOURCE', 'the british council')
        """
    )

    conn.execute(
        """
        INSERT INTO organisation_aliases
        (
            alias_id,
            entity_id,
            organisation_key,
            org_ref,
            alias_name,
            source_system,
            match_method,
            confidence_score
        )
        VALUES
        (
            'ALIAS-1',
            'SOURCE',
            'NAME:the british council',
            '',
            'THE BRITISH COUNCIL',
            'IATI',
            'INITIAL_LOAD',
            1.0
        )
        """
    )

    conn.commit()


def test_merge_moves_alias_and_marks_source():
    conn = make_db()
    seed(conn)

    result = merge_entities(
        conn,
        "SOURCE",
        "TARGET",
    )

    assert result["status"] == "MERGED"
    assert result["aliases_moved"] == 1

    alias = conn.execute(
        """
        SELECT entity_id
        FROM organisation_aliases
        WHERE alias_id = 'ALIAS-1'
        """
    ).fetchone()

    assert alias[0] == "TARGET"

    status = conn.execute(
        """
        SELECT entity_status
        FROM organisation_entities
        WHERE entity_id = 'SOURCE'
        """
    ).fetchone()

    assert status[0] == "MERGED"


def test_merge_records_relationship():
    conn = make_db()
    seed(conn)

    merge_entities(conn, "SOURCE", "TARGET")

    relationship = conn.execute(
        """
        SELECT
            parent_entity_id,
            child_entity_id,
            relationship_type
        FROM organisation_relationships
        """
    ).fetchone()

    assert relationship == (
        "TARGET",
        "SOURCE",
        "MERGED_INTO",
    )


def test_merge_is_idempotent():
    conn = make_db()
    seed(conn)

    first = merge_entities(conn, "SOURCE", "TARGET")
    second = merge_entities(conn, "SOURCE", "TARGET")

    assert first["status"] == "MERGED"
    assert second["status"] == "ALREADY_MERGED"

    count = conn.execute(
        """
        SELECT COUNT(*)
        FROM organisation_relationships
        """
    ).fetchone()[0]

    assert count == 1


def test_cannot_merge_entity_into_itself():
    conn = make_db()
    seed(conn)

    with pytest.raises(ValueError):
        merge_entities(conn, "TARGET", "TARGET")


def test_missing_source_fails():
    conn = make_db()
    seed(conn)

    with pytest.raises(ValueError):
        merge_entities(conn, "DOES_NOT_EXIST", "TARGET")


def test_missing_target_fails():
    conn = make_db()
    seed(conn)

    with pytest.raises(ValueError):
        merge_entities(conn, "SOURCE", "DOES_NOT_EXIST")
