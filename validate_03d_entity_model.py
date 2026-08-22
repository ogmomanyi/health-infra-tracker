#!/usr/bin/env python3
"""Validate the repaired canonical/intelligence organisation model."""

import sqlite3

DB = "data/iati_intelligence.db"


def table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def table_columns(conn, table):
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def count(conn, sql):
    return conn.execute(sql).fetchone()[0]


def reference_check(conn, table, column):
    if not table_exists(conn, table) or column not in table_columns(conn, table):
        return 0
    return count(
        conn,
        f'''
        SELECT COUNT(*) FROM "{table}" t
        LEFT JOIN organisation_entities e ON e.entity_id = t."{column}"
        WHERE t."{column}" IS NOT NULL AND e.entity_id IS NULL
        ''',
    )


def legacy_check(conn, table, column):
    if not table_exists(conn, table) or column not in table_columns(conn, table):
        return 0
    return count(
        conn,
        f'''SELECT COUNT(*) FROM "{table}" WHERE "{column}" LIKE 'ORG-%' ''',
    )


def main():
    conn = sqlite3.connect(DB)
    checks = {}

    entity_schema = {row[1] for row in conn.execute("PRAGMA table_info(organisation_entities)")}
    alias_schema = {row[1] for row in conn.execute("PRAGMA table_info(organisation_aliases)")}

    checks["entity_count"] = count(conn, "SELECT COUNT(*) FROM organisation_entities")
    checks["active_entity_count"] = count(
        conn, "SELECT COUNT(*) FROM organisation_entities WHERE entity_status='ACTIVE'"
    )
    checks["intelligence_rows"] = count(conn, "SELECT COUNT(*) FROM organisation_intelligence")
    checks["intelligence_unmatched"] = reference_check(
        conn, "organisation_intelligence", "organisation_entity_id"
    )
    checks["target_account_unmatched"] = reference_check(
        conn, "target_accounts", "organisation_entity_id"
    )

    checks["reference_unmatched"] = {}
    for table, column in (
        ("organisation_intelligence", "organisation_entity_id"),
        ("target_accounts", "organisation_entity_id"),
        ("recommended_actions", "organisation_entity_id"),
        ("programme_intelligence", "organisation_entity_id"),
        ("donor_intelligence", "organisation_entity_id"),
        ("equipment_entities", "organisation_entity_id"),
        ("opportunity_organisation_resolution", "entity_id"),
        ("organisation_resolution_log", "entity_id"),
        ("organisation_manual_overrides", "entity_id"),
        ("organisation_group_members", "entity_id"),
    ):
        checks["reference_unmatched"][f"{table}.{column}"] = reference_check(conn, table, column)

    checks["legacy_references"] = {}
    for table, column in (
        ("organisation_intelligence", "organisation_entity_id"),
        ("target_accounts", "organisation_entity_id"),
        ("recommended_actions", "organisation_entity_id"),
        ("programme_intelligence", "organisation_entity_id"),
        ("donor_intelligence", "organisation_entity_id"),
        ("equipment_entities", "organisation_entity_id"),
        ("opportunity_organisation_resolution", "entity_id"),
        ("organisation_resolution_log", "entity_id"),
        ("organisation_manual_overrides", "entity_id"),
        ("organisation_group_members", "entity_id"),
    ):
        checks["legacy_references"][f"{table}.{column}"] = legacy_check(conn, table, column)

    checks["relationship_broken"] = count(
        conn,
        """
        SELECT COUNT(*)
        FROM organisation_relationships r
        LEFT JOIN organisation_entities p ON p.entity_id = r.parent_entity_id
        LEFT JOIN organisation_entities c ON c.entity_id = r.child_entity_id
        WHERE p.entity_id IS NULL OR c.entity_id IS NULL
        """,
    )
    checks["relationship_legacy_ids"] = count(
        conn,
        """
        SELECT COUNT(*) FROM organisation_relationships
        WHERE parent_entity_id LIKE 'ORG-%' OR child_entity_id LIKE 'ORG-%'
        """,
    )
    checks["relationship_duplicate_rows"] = count(
        conn,
        """
        SELECT COALESCE(SUM(duplicate_count - 1), 0)
        FROM (
            SELECT COUNT(*) AS duplicate_count
            FROM organisation_relationships
            GROUP BY parent_entity_id, child_entity_id,
                     relationship_type, source_system, confidence_score
            HAVING COUNT(*) > 1
        )
        """,
    )

    checks["opportunity_resolution_bad_entity_ids"] = 0
    if table_exists(conn, "opportunity_organisation_resolution"):
        checks["opportunity_resolution_bad_entity_ids"] = count(
            conn,
            """
            SELECT COUNT(*)
            FROM opportunity_organisation_resolution r
            LEFT JOIN organisation_entities e ON e.entity_id = r.entity_id
            WHERE r.resolution_level = 'ENTITY'
              AND (r.entity_id IS NULL OR e.entity_id IS NULL)
            """,
        )

    checks["canonical_ids_wrong_namespace"] = count(
        conn,
        "SELECT COUNT(*) FROM organisation_entities WHERE entity_id NOT LIKE 'org_%'",
    )
    checks["canonical_name_duplicates"] = count(
        conn,
        """
        SELECT COUNT(*) FROM (
            SELECT canonical_name FROM organisation_entities
            GROUP BY canonical_name HAVING COUNT(*) > 1
        )
        """,
    )

    checks["canonical_schema_ok"] = {
        "entity_id", "canonical_name", "organisation_type", "entity_status",
        "created_at", "updated_at",
    }.issubset(entity_schema)
    checks["aliases_schema_ok"] = {
        "alias_id", "entity_id", "organisation_key", "org_ref", "alias_name",
    }.issubset(alias_schema)

    for key, value in checks.items():
        print(f"{key}: {value}")

    failures = []
    scalar_zero_checks = {
        "intelligence_unmatched", "target_account_unmatched", "relationship_broken",
        "relationship_legacy_ids", "relationship_duplicate_rows",
        "opportunity_resolution_bad_entity_ids", "canonical_ids_wrong_namespace",
        "canonical_name_duplicates",
    }
    failures.extend(name for name in scalar_zero_checks if checks[name] != 0)
    failures.extend(
        f"{name}={value}"
        for name, value in checks["reference_unmatched"].items()
        if value != 0
    )
    failures.extend(
        f"{name}={value}"
        for name, value in checks["legacy_references"].items()
        if value != 0
    )
    failures.extend(
        name for name in ("canonical_schema_ok", "aliases_schema_ok") if not checks[name]
    )

    conn.close()
    if failures:
        raise SystemExit(f"VALIDATION FAILED: {', '.join(failures)}")

    print("VALIDATION PASSED")


if __name__ == "__main__":
    main()
