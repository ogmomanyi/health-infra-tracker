#!/usr/bin/env python3
"""Validate that downstream organisation references point to canonical roots."""

import sqlite3

from organisation_resolution.database_resolver import get_canonical_entity_id

DB = "data/iati_intelligence.db"

REFERENCE_COLUMNS = {
    "organisation_intelligence": ["organisation_entity_id"],
    "target_accounts": ["organisation_entity_id"],
    "recommended_actions": ["organisation_entity_id"],
    "programme_intelligence": ["organisation_entity_id"],
    "donor_intelligence": ["organisation_entity_id"],
    "equipment_entities": ["organisation_entity_id"],
    "opportunity_organisation_resolution": ["entity_id"],
    "organisation_resolution_log": ["entity_id"],
    "organisation_manual_overrides": ["entity_id"],
    "organisation_group_members": ["entity_id"],
}


def table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def table_columns(conn, table):
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def main():
    conn = sqlite3.connect(DB)
    failures = []
    checked = 0

    for table, columns in REFERENCE_COLUMNS.items():
        if not table_exists(conn, table):
            continue
        available = table_columns(conn, table)
        for column in columns:
            if column not in available:
                continue
            rows = conn.execute(
                f'SELECT rowid, "{column}" FROM "{table}" '
                f'WHERE "{column}" IS NOT NULL AND "{column}" != ""'
            ).fetchall()
            for rowid, entity_id in rows:
                checked += 1
                canonical = get_canonical_entity_id(conn, entity_id)
                if canonical != entity_id:
                    failures.append((table, column, rowid, entity_id, canonical))

    conn.close()

    print(f"Organisation references checked: {checked}")
    print(f"Non-canonical references: {len(failures)}")

    if failures:
        for failure in failures[:100]:
            print("NON_CANONICAL", failure)
        raise SystemExit("CANONICAL REFERENCE VALIDATION FAILED")

    print("CANONICAL REFERENCE VALIDATION PASSED")


if __name__ == "__main__":
    main()
