import sqlite3

from organisation_resolution.database_writer import (
    persist_resolution,
)


def create_test_database():
    conn = sqlite3.connect(":memory:")

    conn.execute(
        """
        CREATE TABLE organisation_entities (
            entity_id TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
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
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE organisation_resolution_log (
            resolution_id TEXT PRIMARY KEY,
            alias_id TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            resolution_action TEXT NOT NULL,
            resolution_rule TEXT,
            confidence_score REAL,
            resolved_by TEXT DEFAULT 'SYSTEM'
        )
        """
    )

    conn.execute(
        """
        INSERT INTO organisation_entities
        (
            entity_id,
            canonical_name
        )
        VALUES
        (
            'ORG-001',
            'world health organization'
        )
        """
    )

    return conn


def test_persist_resolution():

    conn = create_test_database()

    resolution = {
        "organisation_key": "REF:WHO-NEW",
        "org_ref": "WHO-NEW",
        "alias_name": "World Health Organization",
        "entity_id": "ORG-001",
        "match_method": "EXACT_MATCH",
        "confidence_score": 1.0,
        "resolution_action": "MATCHED",
    }

    result = persist_resolution(
        conn,
        resolution,
    )

    assert result["created"] is True

    alias = conn.execute(
        """
        SELECT
            entity_id,
            organisation_key,
            alias_name,
            match_method,
            confidence_score
        FROM organisation_aliases
        """
    ).fetchone()

    assert alias == (
        "ORG-001",
        "REF:WHO-NEW",
        "World Health Organization",
        "EXACT_MATCH",
        1.0,
    )

    log = conn.execute(
        """
        SELECT
            entity_id,
            resolution_action,
            resolution_rule,
            confidence_score
        FROM organisation_resolution_log
        """
    ).fetchone()

    assert log == (
        "ORG-001",
        "MATCHED",
        "EXACT_MATCH",
        1.0,
    )

    conn.close()


def test_persist_resolution_is_idempotent():

    conn = create_test_database()

    resolution = {
        "organisation_key": "REF:WHO-NEW",
        "org_ref": "WHO-NEW",
        "alias_name": "World Health Organization",
        "entity_id": "ORG-001",
        "match_method": "EXACT_MATCH",
        "confidence_score": 1.0,
        "resolution_action": "MATCHED",
    }

    first = persist_resolution(
        conn,
        resolution,
    )

    second = persist_resolution(
        conn,
        resolution,
    )

    assert first["created"] is True
    assert second["created"] is False

    alias_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM organisation_aliases
        """
    ).fetchone()[0]

    assert alias_count == 1

    log_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM organisation_resolution_log
        """
    ).fetchone()[0]

    assert log_count == 2

    conn.close()
