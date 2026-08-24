import sqlite3

from organisation_resolution.database_resolver import get_canonical_entity_id
from organisation_resolution.opportunity_group_resolver import (
    classify_non_entity,
    load_group_aliases,
    load_group_keys,
    resolve_group,
)


def make_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE organisation_entities (
            entity_id TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL,
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

        CREATE TABLE organisation_groups (
            group_id TEXT PRIMARY KEY,
            group_name TEXT NOT NULL,
            canonical_group_key TEXT NOT NULL UNIQUE,
            group_status TEXT NOT NULL DEFAULT 'ACTIVE'
        );

        CREATE TABLE organisation_group_members (
            group_id TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            source_system TEXT NOT NULL DEFAULT 'SYSTEM_GROUP_SEED',
            PRIMARY KEY (group_id, entity_id)
        );
        """
    )
    return conn


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


def test_explicit_group_alias_wins_over_ambiguous_membership_alias():
    conn = make_db()
    conn.executemany(
        """
        INSERT INTO organisation_entities(entity_id, canonical_name)
        VALUES (?, ?)
        """,
        [
            ("org_unicef_child", "Clinton Health Access Initiative"),
            ("org_chai", "Clinton Health Access Initiative"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO organisation_groups(group_id, group_name, canonical_group_key)
        VALUES (?, ?, ?)
        """,
        [
            ("grp_unicef", "UNICEF", "UNICEF"),
            (
                "grp_chai",
                "Clinton Health Access Initiative",
                "CLINTON_HEALTH_ACCESS_INITIATIVE",
            ),
        ],
    )
    conn.executemany(
        """
        INSERT INTO organisation_group_members(group_id, entity_id)
        VALUES (?, ?)
        """,
        [
            ("grp_unicef", "org_unicef_child"),
            ("grp_chai", "org_chai"),
        ],
    )

    result = resolve_group(
        "Clinton Health Access Initiative",
        load_group_aliases(conn),
        load_group_keys(conn),
    )

    assert result == ("grp_chai", "Clinton Health Access Initiative")
    conn.close()


def test_known_opportunity_aliases_resolve_to_groups():
    conn = make_db()
    conn.executemany(
        """
        INSERT INTO organisation_groups(group_id, group_name, canonical_group_key)
        VALUES (?, ?, ?)
        """,
        [
            ("grp_fcdo", "Foreign, Commonwealth & Development Office", "FCDO"),
            ("grp_who", "World Health Organization", "WORLD_HEALTH_ORGANIZATION"),
            ("grp_amref", "AMREF Health Africa", "AMREF"),
        ],
    )

    group_keys = load_group_keys(conn)

    assert resolve_group("DFID", {}, group_keys) == (
        "grp_fcdo",
        "Foreign, Commonwealth & Development Office",
    )
    assert resolve_group("WHO - World Health Organization", {}, group_keys) == (
        "grp_who",
        "World Health Organization",
    )
    assert resolve_group("Amref UK", {}, group_keys) == (
        "grp_amref",
        "AMREF Health Africa",
    )
    conn.close()


def test_placeholder_opportunity_references_are_non_entities():
    assert classify_non_entity("IP not published")
    assert classify_non_entity("Anonymous")
    assert classify_non_entity("Long programme description\nwith a second line")
