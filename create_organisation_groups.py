import sqlite3
import uuid

DB = "data/iati_intelligence.db"


def table_exists(conn, table_name):
    return conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (table_name,),
    ).fetchone() is not None


conn = sqlite3.connect(DB)

try:
    conn.execute("PRAGMA foreign_keys = ON")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS organisation_groups (
            group_id TEXT PRIMARY KEY,
            group_name TEXT NOT NULL,
            canonical_group_key TEXT NOT NULL UNIQUE,
            group_type TEXT NOT NULL DEFAULT 'ORGANISATION_FAMILY',
            group_status TEXT NOT NULL DEFAULT 'ACTIVE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS organisation_group_members (
            group_id TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            membership_type TEXT NOT NULL DEFAULT 'MEMBER',
            confidence_score REAL NOT NULL DEFAULT 1.0,
            source_system TEXT NOT NULL DEFAULT 'MANUAL_AUDIT',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (group_id, entity_id),

            FOREIGN KEY (group_id)
                REFERENCES organisation_groups(group_id),

            FOREIGN KEY (entity_id)
                REFERENCES organisation_entities(entity_id)
        )
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_org_group_members_entity
        ON organisation_group_members(entity_id)
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_org_group_members_group
        ON organisation_group_members(group_id)
        """
    )

    conn.commit()

    print("Organisation group schema created successfully.")

finally:
    conn.close()
