#!/usr/bin/env python3
"""Validate the repaired canonical/intelligence organisation model."""

import sqlite3

DB = "data/iati_intelligence.db"


def main():
    conn = sqlite3.connect(DB)

    checks = {}

    checks["canonical_entity_schema"] = [
        row[1] for row in conn.execute("PRAGMA table_info(organisation_entities)")
    ]
    checks["alias_schema"] = [
        row[1] for row in conn.execute("PRAGMA table_info(organisation_aliases)")
    ]

    checks["entity_count"] = conn.execute(
        "SELECT COUNT(*) FROM organisation_entities"
    ).fetchone()[0]
    checks["active_entity_count"] = conn.execute(
        "SELECT COUNT(*) FROM organisation_entities WHERE entity_status='ACTIVE'"
    ).fetchone()[0]
    checks["intelligence_rows"] = conn.execute(
        "SELECT COUNT(*) FROM organisation_intelligence"
    ).fetchone()[0]

    checks["intelligence_unmatched"] = conn.execute(
        """
        SELECT COUNT(*)
        FROM organisation_intelligence oi
        LEFT JOIN organisation_entities oe
          ON oe.entity_id = oi.organisation_entity_id
        WHERE oe.entity_id IS NULL
        """
    ).fetchone()[0]

    checks["target_account_unmatched"] = conn.execute(
        """
        SELECT COUNT(*)
        FROM target_accounts ta
        LEFT JOIN organisation_entities oe
          ON oe.entity_id = ta.organisation_entity_id
        WHERE oe.entity_id IS NULL
        """
    ).fetchone()[0]

    checks["relationship_broken"] = conn.execute(
        """
        SELECT COUNT(*)
        FROM organisation_relationships r
        LEFT JOIN organisation_entities p
          ON p.entity_id = r.parent_entity_id
        LEFT JOIN organisation_entities c
          ON c.entity_id = r.child_entity_id
        WHERE p.entity_id IS NULL OR c.entity_id IS NULL
        """
    ).fetchone()[0]

    checks["duplicate_relationships"] = conn.execute(
        """
        SELECT COUNT(*)
        FROM organisation_relationships
        WHERE relationship_type='DUPLICATE_OF'
        """
    ).fetchone()[0]

    checks["canonical_schema_ok"] = {
        "entity_id",
        "canonical_name",
        "organisation_type",
        "entity_status",
        "created_at",
        "updated_at",
    }.issubset(set(checks["canonical_entity_schema"]))

    checks["aliases_schema_ok"] = {
        "alias_id",
        "entity_id",
        "organisation_key",
        "org_ref",
        "alias_name",
    }.issubset(set(checks["alias_schema"]))

    for key, value in checks.items():
        print(f"{key}: {value}")

    failures = [
        name for name, value in checks.items()
        if name.endswith("_unmatched") or name.endswith("_broken")
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
