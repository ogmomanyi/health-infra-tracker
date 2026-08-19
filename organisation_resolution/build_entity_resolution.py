"""
Build Organisation Entity Resolution Layer

Reads source organisations from organisation_intelligence
and populates:

- organisation_entities
- organisation_aliases
- organisation_resolution_log
"""

import sqlite3
import uuid

from organisation_resolution.normalizer import normalize_name


DB_PATH = "data/iati_intelligence.db"


def generate_entity_id():
    return f"ORG-{uuid.uuid4().hex[:8].upper()}"


def load_source_organisations(conn):
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            organisation_key,
            org_ref,
            org_name
        FROM organisation_intelligence
        WHERE org_name IS NOT NULL
    """)

    return cursor.fetchall()


def create_entity(conn, canonical_name):
    entity_id = generate_entity_id()

    conn.execute(
        """
        INSERT INTO organisation_entities
        (
            entity_id,
            canonical_name
        )
        VALUES (?,?)
        """,
        (
            entity_id,
            canonical_name
        )
    )

    return entity_id


def create_alias(
    conn,
    entity_id,
    organisation_key,
    org_ref,
    alias_name
):

    conn.execute(
        """
        INSERT INTO organisation_aliases
        (
            alias_id,
            entity_id,
            organisation_key,
            org_ref,
            alias_name,
            is_primary_alias,
            match_method,
            confidence_score
        )
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            str(uuid.uuid4()),
            entity_id,
            organisation_key,
            org_ref,
            alias_name,
            1,
            "INITIAL_LOAD",
            1.0
        )
    )


def build_resolution():

    conn = sqlite3.connect(DB_PATH)

    organisations = load_source_organisations(conn)

    print(
        f"Loaded {len(organisations)} organisations"
    )

    created = 0


    for organisation in organisations:

        organisation_key, org_ref, org_name = organisation


        canonical_name = normalize_name(
            org_name
        )


        existing = conn.execute(
            """
            SELECT entity_id
            FROM organisation_entities
            WHERE canonical_name = ?
            """,
            (
                canonical_name,
            )
        ).fetchone()


        if existing:

            entity_id = existing[0]

        else:

            entity_id = create_entity(
                conn,
                canonical_name
            )

            created += 1


        create_alias(
            conn,
            entity_id,
            organisation_key,
            org_ref,
            org_name
        )


    conn.commit()

    conn.close()


    print(
        f"Created {created} new entities"
    )


if __name__ == "__main__":
    build_resolution()