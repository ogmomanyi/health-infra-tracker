import sqlite3

DB = "data/iati_intelligence.db"

conn = sqlite3.connect(DB)

try:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS opportunity_organisation_resolution (
            resolution_id INTEGER PRIMARY KEY AUTOINCREMENT,

            opportunity_id TEXT NOT NULL,
            organisation_name TEXT NOT NULL,
            organisation_role TEXT NOT NULL,

            entity_id TEXT,
            group_id TEXT,

            resolution_level TEXT NOT NULL,

            confidence_score REAL NOT NULL DEFAULT 0.0,

            resolution_method TEXT NOT NULL,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (entity_id)
                REFERENCES organisation_entities(entity_id),

            FOREIGN KEY (group_id)
                REFERENCES organisation_groups(group_id),

            CHECK (
                resolution_level IN (
                    'ENTITY',
                    'GROUP',
                    'UNRESOLVED',
                    'NON_ENTITY'
                )
            )
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_oor_opportunity
        ON opportunity_organisation_resolution(opportunity_id)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_oor_entity
        ON opportunity_organisation_resolution(entity_id)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_oor_group
        ON opportunity_organisation_resolution(group_id)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_oor_role
        ON opportunity_organisation_resolution(organisation_role)
    """)

    conn.commit()

    print("Opportunity organisation resolution schema created successfully.")

finally:
    conn.close()
