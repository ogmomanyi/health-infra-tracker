#!/usr/bin/env python3
"""Validate the repaired canonical/intelligence organisation model."""

import sqlite3

DB = "data/iati_intelligence.db"


def table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def count(conn, sql):
    return conn.execute(sql).fetchone()[0]


def main():
    conn = sqlite3.connect(DB)
    checks = {}

    checks["canonical_entity_schema"] = [
        row[1] for row in conn.execute("PRAGMA table_info(organisation_entities)")
    ]
    checks["alias_schema"] = [
        row[1] for row in conn.execute("PRAGMA table_info(organisation_aliases)")
    ]

    checks["entity_count"] = count(conn, "SELECT COUNT(*) FROM organisation_entities")
    checks["active_entity_count"] = count(
        conn, "SELECT COUNT(*) FROM organisation_entities WHERE entity_status='ACTIVE'"
    )
    checks["intelligence_rows"] = count(conn, "SELECT COUNT(*) FROM organisation_intelligence")

    checks["intelligence_unmatched"] = count(
        conn,
        """
        SELECT COUNT(*)
        FROM organisation_intelligence oi
        LEFT JOIN organisation_entities oe ON oe.entity_id = oi.organisation_entity_id
        WHERE oe.entity_id IS NULL
        """,
    )
    checks["target_account_unmatched"] = count(
        conn,
        """
        SELECT COUNT(*)
        FROM target_accounts ta
        LEFT JOIN organisation_entities oe ON oe.entity_id = ta.organisation_entity_id
        WHERE oe.entity_id IS NULL
        """,
    )
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

    checks["group_member_broken"] = 0
    if table_exists(conn, "organisation_group_members"):
        checks["group_member_broken"] = count(
            conn,
            """
            SELECT COUNT(*)
            FROM organisation_group_members m
            LEFT JOIN organisation_entities e ON e.entity_id = m.entity_id
            WHERE e.entity_id IS NULL
            """,
        )

    checks["group_member_legacy_ids"] = 0
    if table_exists(conn, "organisation_group_members"):
        checks["group_member_legacy_ids"] = count(
            conn,
            "SELECT COUNT(*) FROM organisation_group_members WHERE entity_id LIKE 'ORG-%'",
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

    checks["opportunity_resolution_legacy_ids"] = 0
    if table_exists(conn, "opportunity_organisation_resolution"):
        checks["opportunity_resolution_legacy_ids"] = count(
            conn,
            """
            SELECT COUNT(*) FROM opportunity_organisation_resolution
            WHERE entity_id LIKE 'ORG-%'
            """,
        )

    checks["canonical_ids_wrong_namespace"] = count(
        conn,
        """
        SELECT COUNT(*) FROM organisation_entities
        WHERE entity_id NOT LIKE 'org_%'
        """,
    )

    checks["canonical_schema_ok"] = {
        "entity_id", "canonical_name", "organisation_type",
        "entity_status", "created_at", "updated_at",
    }.issubset(set(checks["canonical_entity_schema"]))
    checks["aliases_schema_ok"] = {
        "alias_id", "entity_id", "organisation_key", "org_ref", "alias_name",
    }.issubset(set(checks["alias_schema"]))

    for key, value in checks.items():
        print(f"{key}: {value}")

    failures = [
        name for name, value in checks.items()
        if name.endswith("_unmatched")
        or name.endswith("_broken")
        or name.endswith("_legacy_ids")
        or name in {
            "relationship_duplicate_rows",
            "opportunity_resolution_bad_entity_ids",
            "canonical_ids_wrong_namespace",
        }
        if value != 0
    ]
    failures += [
        name for name in ("canonical_schema_ok", "aliases_schema_ok")
        if not checks[name]
    ]

    conn.close()

    if failures:
        raise SystemExit(f"VALIDATION FAILED: {', '.join(failures)}")

    print("VALIDATION PASSED")


if __name__ == "__main__":
    main()
