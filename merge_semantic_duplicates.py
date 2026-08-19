import sqlite3
import uuid

DB = "data/iati_intelligence.db"

MERGES = [
    # canonical, duplicate, reason
    (
        "ORG-196E18DB",
        "ORG-BA66B6F7",
        "Semantic duplicate: British Council vs The British Council",
    ),
    (
        "ORG-81BA5F48",
        "ORG-35956085",
        "Semantic duplicate: Malawi Liverpool Wellcome Trust Clinical Research Programme",
    ),
    (
        "ORG-3168C727",
        "ORG-395981B7",
        "Semantic duplicate: Pandemic Fund vs The Pandemic Fund",
    ),
    (
        "ORG-C514FA9E",
        "ORG-1EC0D518",
        "Semantic duplicate: University of Manchester vs The University of Manchester",
    ),
    (
        "ORG-1DA8CDEF",
        "ORG-8007CDFA",
        "Semantic duplicate: University of Oxford vs The University of Oxford",
    ),
    (
        "ORG-FAAB7F05",
        "ORG-5C581736",
        "Semantic duplicate: William and Flora Hewlett Foundation",
    ),
    (
        "ORG-03F8DA19",
        "ORG-B93FBED0",
        "Semantic duplicate: World Bank vs The World Bank",
    ),
]


def entity_exists(conn, entity_id):
    return conn.execute(
        """
        SELECT 1
        FROM organisation_entities
        WHERE entity_id = ?
        """,
        (entity_id,),
    ).fetchone() is not None


conn = sqlite3.connect(DB)

try:
    conn.execute("BEGIN")

    for parent_id, child_id, reason in MERGES:

        if not entity_exists(conn, parent_id):
            raise RuntimeError(f"Canonical entity does not exist: {parent_id}")

        if not entity_exists(conn, child_id):
            raise RuntimeError(f"Duplicate entity does not exist: {child_id}")

        existing = conn.execute(
            """
            SELECT relationship_id
            FROM organisation_relationships
            WHERE parent_entity_id = ?
              AND child_entity_id = ?
              AND relationship_type = 'DUPLICATE_OF'
            """,
            (parent_id, child_id),
        ).fetchone()

        if existing:
            print(f"EXISTS  {parent_id} <- {child_id}")
            continue

        relationship_id = str(uuid.uuid4())

        conn.execute(
            """
            INSERT INTO organisation_relationships (
                relationship_id,
                parent_entity_id,
                child_entity_id,
                relationship_type,
                source_system,
                confidence_score
            )
            VALUES (?, ?, ?, 'DUPLICATE_OF', 'MANUAL_AUDIT', 1.0)
            """,
            (
                relationship_id,
                parent_id,
                child_id,
            ),
        )

        print(f"ADDED   {parent_id} <- {child_id}")
        print(f"        {reason}")

    conn.commit()

except Exception:
    conn.rollback()
    raise

finally:
    conn.close()

print()
print("Semantic duplicate relationships created successfully.")
