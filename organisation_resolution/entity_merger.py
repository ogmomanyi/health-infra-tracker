"""
Safe database operations for organisation entity consolidation.

Entity resolution produces decisions; this module applies approved
entity merges while preserving aliases and maintaining an audit trail.
"""

import sqlite3
import uuid
from datetime import datetime, timezone


MERGED_STATUS = "MERGED"
RELATIONSHIP_TYPE = "MERGED_INTO"
SOURCE_SYSTEM = "ENTITY_RESOLUTION"


def _new_id():
    return str(uuid.uuid4())


def merge_entities(
    conn,
    source_entity_id,
    target_entity_id,
    reason="semantic_duplicate",
    confidence_score=1.0,
):
    """
    Merge source_entity_id into target_entity_id.

    The target remains ACTIVE.
    The source is marked MERGED.
    All source aliases are reassigned to the target.
    A MERGED_INTO relationship is recorded.

    The operation is transactional and idempotent.
    """

    if source_entity_id == target_entity_id:
        raise ValueError("Source and target entities must be different")

    conn.execute("BEGIN")

    try:
        source = conn.execute(
            """
            SELECT entity_id, canonical_name, entity_status
            FROM organisation_entities
            WHERE entity_id = ?
            """,
            (source_entity_id,),
        ).fetchone()

        target = conn.execute(
            """
            SELECT entity_id, canonical_name, entity_status
            FROM organisation_entities
            WHERE entity_id = ?
            """,
            (target_entity_id,),
        ).fetchone()

        if source is None:
            raise ValueError(
                f"Source entity does not exist: {source_entity_id}"
            )

        if target is None:
            raise ValueError(
                f"Target entity does not exist: {target_entity_id}"
            )

        source_status = source[2]
        target_status = target[2]

        if target_status != "ACTIVE":
            raise ValueError(
                f"Target entity must be ACTIVE: {target_entity_id}"
            )

        # Idempotency: if already merged into this target, do nothing.
        existing_relationship = conn.execute(
            """
            SELECT relationship_id
            FROM organisation_relationships
            WHERE parent_entity_id = ?
              AND child_entity_id = ?
              AND relationship_type = ?
            """,
            (
                target_entity_id,
                source_entity_id,
                RELATIONSHIP_TYPE,
            ),
        ).fetchone()

        if existing_relationship:
            conn.commit()
            return {
                "source_entity_id": source_entity_id,
                "target_entity_id": target_entity_id,
                "status": "ALREADY_MERGED",
                "aliases_moved": 0,
            }

        if source_status != "ACTIVE":
            raise ValueError(
                f"Source entity must be ACTIVE: {source_entity_id}"
            )

        # Check for alias collisions before changing anything.
        source_aliases = conn.execute(
            """
            SELECT
                alias_id,
                organisation_key,
                org_ref,
                alias_name,
                source_system
            FROM organisation_aliases
            WHERE entity_id = ?
            ORDER BY alias_id
            """,
            (source_entity_id,),
        ).fetchall()

        aliases_moved = 0

        for (
            alias_id,
            organisation_key,
            org_ref,
            alias_name,
            source_system,
        ) in source_aliases:

            collision = conn.execute(
                """
                SELECT alias_id, entity_id
                FROM organisation_aliases
                WHERE alias_name = ?
                  AND entity_id = ?
                  AND source_system = ?
                """,
                (
                    alias_name,
                    target_entity_id,
                    source_system,
                ),
            ).fetchone()

            if collision:
                # Same alias already exists on target.
                # Delete the duplicate source alias rather than
                # creating two identical aliases.
                conn.execute(
                    """
                    DELETE FROM organisation_aliases
                    WHERE alias_id = ?
                    """,
                    (alias_id,),
                )
            else:
                conn.execute(
                    """
                    UPDATE organisation_aliases
                    SET entity_id = ?
                    WHERE alias_id = ?
                    """,
                    (target_entity_id, alias_id),
                )

            aliases_moved += 1

        # Record the relationship.
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
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _new_id(),
                target_entity_id,
                source_entity_id,
                RELATIONSHIP_TYPE,
                SOURCE_SYSTEM,
                confidence_score,
            ),
        )

        # Preserve the source entity as historical evidence.
        now = datetime.now(timezone.utc).isoformat()

        conn.execute(
            """
            UPDATE organisation_entities
            SET entity_status = ?,
                updated_at = ?
            WHERE entity_id = ?
            """,
            (
                MERGED_STATUS,
                now,
                source_entity_id,
            ),
        )

        conn.commit()

        return {
            "source_entity_id": source_entity_id,
            "target_entity_id": target_entity_id,
            "status": "MERGED",
            "aliases_moved": aliases_moved,
            "reason": reason,
        }

    except Exception:
        conn.rollback()
        raise
