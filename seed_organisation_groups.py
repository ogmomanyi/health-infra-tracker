import sqlite3
import uuid

DB = "data/iati_intelligence.db"

GROUPS = {
    "EUROPEAN_COMMISSION": {
        "name": "European Commission",
        "entities": [
            "ORG-C9C27FEB",
            "ORG-4E60516F",
            "ORG-CECD9456",
            "ORG-9B86570E",
            "ORG-D435A4C2",
        ],
    },
    "CORDAID": {
        "name": "Cordaid",
        "entities": [
            "ORG-61D4B00F",
        ],
    },
    "INTERNATIONAL_RESCUE_COMMITTEE": {
        "name": "International Rescue Committee",
        "entities": [
            "ORG-E5A51FB9",
            "ORG-91596D3F",
            "ORG-C4A8FD0D",
            "ORG-20DEB1F4",
        ],
    },
    "CLINTON_HEALTH_ACCESS_INITIATIVE": {
        "name": "Clinton Health Access Initiative",
        "entities": [
            "ORG-532C5A40",
            "ORG-245A8641",
        ],
    },
    "GLOBAL_FUND": {
        "name": "Global Fund",
        "entities": [
            "ORG-B72D16F5",
            "ORG-DFEAC78B",
        ],
    },
}


conn = sqlite3.connect(DB)

try:
    conn.execute("PRAGMA foreign_keys = ON")

    for group_key, definition in GROUPS.items():
        group_id = (
            conn.execute(
                """
                SELECT group_id
                FROM organisation_groups
                WHERE canonical_group_key = ?
                """,
                (group_key,),
            ).fetchone()
        )

        if group_id:
            group_id = group_id[0]
        else:
            group_id = f"GRP-{uuid.uuid4().hex[:8].upper()}"

            conn.execute(
                """
                INSERT INTO organisation_groups (
                    group_id,
                    group_name,
                    canonical_group_key,
                    group_type,
                    group_status
                )
                VALUES (?, ?, ?, 'ORGANISATION_FAMILY', 'ACTIVE')
                """,
                (
                    group_id,
                    definition["name"],
                    group_key,
                ),
            )

        for entity_id in definition["entities"]:
            entity = conn.execute(
                """
                SELECT entity_id, canonical_name
                FROM organisation_entities
                WHERE entity_id = ?
                """,
                (entity_id,),
            ).fetchone()

            if not entity:
                print(
                    f"WARNING: entity {entity_id} does not exist; "
                    f"skipping."
                )
                continue

            conn.execute(
                """
                INSERT OR IGNORE INTO organisation_group_members (
                    group_id,
                    entity_id,
                    membership_type,
                    confidence_score,
                    source_system
                )
                VALUES (?, ?, 'MEMBER', 1.0, 'MANUAL_AUDIT')
                """,
                (group_id, entity_id),
            )

    conn.commit()

    print("Organisation groups seeded successfully.")

finally:
    conn.close()
