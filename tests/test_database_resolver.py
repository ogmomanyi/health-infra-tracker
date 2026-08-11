import sqlite3

from organisation_resolution.database_resolver import (
    load_entity_candidates,
    load_alias_candidates,
    load_candidates,
    resolve_source_record,
)


def create_test_database():
    conn = sqlite3.connect(":memory:")

    conn.execute(
        """
        CREATE TABLE organisation_entities (
            entity_id TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            organisation_type TEXT,
            entity_status TEXT DEFAULT 'ACTIVE'
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
        CREATE TABLE organisation_relationships (
            relationship_id TEXT PRIMARY KEY,
            parent_entity_id TEXT NOT NULL,
            child_entity_id TEXT NOT NULL,
            relationship_type TEXT NOT NULL,
            source_system TEXT NOT NULL DEFAULT 'IATI',
            confidence_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

    conn.execute(
        """
        INSERT INTO organisation_entities
        (
            entity_id,
            canonical_name
        )
        VALUES
        (
            'ORG-002',
            'amref health africa'
        )
        """
    )

    conn.execute(
        """
        INSERT INTO organisation_aliases
        (
            alias_id,
            entity_id,
            organisation_key,
            alias_name,
            match_method
        )
        VALUES
        (
            'ALIAS-001',
            'ORG-001',
            'REF:WHO',
            'WHO',
            'INITIAL_LOAD'
        )
        """
    )

    conn.execute(
        """
        INSERT INTO organisation_entities
        (
            entity_id,
            canonical_name,
            entity_status
        )
        VALUES
        (
            'ORG-003',
            'university of oxford',
            'INACTIVE'
        )
        """
    )

    conn.execute(
        """
        INSERT INTO organisation_entities
        (
            entity_id,
            canonical_name,
            entity_status
        )
        VALUES
        (
            'ORG-004',
            'the university of oxford',
            'INACTIVE'
        )
        """
    )

    conn.execute(
        """
        INSERT INTO organisation_relationships
        (
            relationship_id,
            parent_entity_id,
            child_entity_id,
            relationship_type,
            source_system,
            confidence_score
        )
        VALUES
        (
            'REL-001',
            'ORG-003',
            'ORG-004',
            'DUPLICATE_OF',
            'TEST',
            1.0
        )
        """
    )

    return conn


def test_load_entity_candidates():

    conn = create_test_database()

    candidates = load_entity_candidates(conn)

    assert len(candidates) == 2

    assert any(
        candidate["entity_id"] == "ORG-001"
        for candidate in candidates
    )

    conn.close()


def test_load_alias_candidates():

    conn = create_test_database()

    candidates = load_alias_candidates(conn)

    assert any(
        candidate["entity_id"] == "ORG-001"
        and candidate["normalized_name"] == "who"
        for candidate in candidates
    )

    conn.close()


def test_resolve_using_canonical_name():

    conn = create_test_database()

    candidates = load_candidates(conn)

    result = resolve_source_record(
        conn,
        {
            "organisation_key": "REF:WHO-NEW",
            "org_ref": "WHO-NEW",
            "org_name": "World Health Organization",
        },
        candidates,
    )

    assert result["entity_id"] == "ORG-001"
    assert result["resolution_action"] == "MATCHED"

    conn.close()


def test_resolve_using_alias():

    conn = create_test_database()

    candidates = load_candidates(conn)

    result = resolve_source_record(
        conn,
        {
            "organisation_key": "REF:WHO-ALIAS",
            "org_ref": "WHO",
            "org_name": "WHO",
        },
        candidates,
    )

    assert result["entity_id"] == "ORG-001"
    assert result["resolution_action"] == "MATCHED"

    conn.close()
    
def test_non_entity_placeholder_is_excluded():

    conn = create_test_database()

    candidates = load_candidates(conn)

    result = resolve_source_record(
        conn,
        {
            "organisation_key": "REF:UNKNOWN",
            "org_ref": "UNKNOWN",
            "org_name": "IP not published",
        },
        candidates,
    )

    assert result["entity_id"] is None
    assert result["match_method"] == "NON_ENTITY"
    assert result["confidence_score"] == 0.0
    assert result["resolution_action"] == "EXCLUDED"

    conn.close()

def test_anonymous_is_excluded():

    conn = create_test_database()

    candidates = load_candidates(conn)

    result = resolve_source_record(
        conn,
        {
            "organisation_key": "NAME:anonymous",
            "org_ref": "",
            "org_name": "Anonymous",
        },
        candidates,
    )

    assert result["entity_id"] is None
    assert result["match_method"] == "NON_ENTITY"
    assert result["resolution_action"] == "EXCLUDED"

    conn.close()     

def test_duplicate_entity_resolves_to_canonical():
    conn = create_test_database()

    from organisation_resolution.database_resolver import (
        get_canonical_entity_id,
    )

    result = get_canonical_entity_id(
        conn,
        "ORG-004",
    )

    assert result == "ORG-003"

    conn.close()


def test_canonical_entity_remains_unchanged():
    conn = create_test_database()

    from organisation_resolution.database_resolver import (
        get_canonical_entity_id,
    )

    result = get_canonical_entity_id(
        conn,
        "ORG-003",
    )

    assert result == "ORG-003"

    conn.close()


def test_relationship_cycle_is_detected():
    conn = create_test_database()

    from organisation_resolution.database_resolver import (
        get_canonical_entity_id,
    )

    conn.execute(
        """
        INSERT INTO organisation_relationships
        (
            relationship_id,
            parent_entity_id,
            child_entity_id,
            relationship_type
        )
        VALUES
        (
            'REL-002',
            'ORG-004',
            'ORG-003',
            'DUPLICATE_OF'
        )
        """
    )

    try:
        get_canonical_entity_id(conn, "ORG-003")
        assert False, "Expected relationship cycle to raise RuntimeError"
    except RuntimeError as exc:
        assert "Cycle detected" in str(exc)

    conn.close()

def test_placeholder_entities_are_not_loaded_as_candidates():
    conn = create_test_database()

    conn.execute("""
        INSERT INTO organisation_entities
        (entity_id, canonical_name, entity_status)
        VALUES
        ('ORG-PLACEHOLDER-001', 'anonymous', 'INACTIVE'),
        ('ORG-PLACEHOLDER-002', 'undefined', 'INACTIVE')
    """)

    conn.commit()

    candidates = load_entity_candidates(conn)

    entity_ids = {candidate["entity_id"] for candidate in candidates}

    assert "ORG-PLACEHOLDER-001" not in entity_ids
    assert "ORG-PLACEHOLDER-002" not in entity_ids