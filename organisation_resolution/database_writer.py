"""
Database writer for Organisation Entity Resolution.

Persists resolution decisions produced by database_resolver.py.

This module:
- creates organisation aliases for matched records
- records resolution decisions
- is safe to run repeatedly
- does not perform matching itself
"""

import sqlite3
import uuid


def persist_resolution(conn, resolution):
    """
    Persist a single organisation resolution.

    Returns:
        {
            "created": True/False,
            "alias_id": "...",
            "resolution_id": "..."
        }
    """

    organisation_key = resolution["organisation_key"]
    org_ref = resolution.get("org_ref")
    alias_name = resolution["alias_name"]
    entity_id = resolution["entity_id"]
    match_method = resolution["match_method"]
    confidence_score = resolution["confidence_score"]
    resolution_action = resolution["resolution_action"]

    # ---------------------------------------------------------
    # Only matched resolutions should create aliases.
    # ---------------------------------------------------------

    if resolution_action != "MATCHED":
        return {
            "created": False,
            "alias_id": None,
            "resolution_id": None,
        }

    # ---------------------------------------------------------
    # Check whether this source record already has an alias.
    # ---------------------------------------------------------

    existing = conn.execute(
        """
        SELECT alias_id
        FROM organisation_aliases
        WHERE organisation_key = ?
        """,
        (organisation_key,),
    ).fetchone()

    if existing:
        alias_id = existing[0]
        created = False

    else:
        alias_id = str(uuid.uuid4())

        conn.execute(
            """
            INSERT INTO organisation_aliases
            (
                alias_id,
                entity_id,
                organisation_key,
                org_ref,
                alias_name,
                source_system,
                is_primary_alias,
                match_method,
                confidence_score
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alias_id,
                entity_id,
                organisation_key,
                org_ref,
                alias_name,
                "IATI",
                0,
                match_method,
                confidence_score,
            ),
        )

        created = True

    # ---------------------------------------------------------
    # Always record the resolution decision.
    #
    # This gives us an audit trail even when the alias already
    # existed and the operation was therefore idempotent.
    # ---------------------------------------------------------

    resolution_id = str(uuid.uuid4())

    conn.execute(
        """
        INSERT INTO organisation_resolution_log
        (
            resolution_id,
            alias_id,
            entity_id,
            resolution_action,
            resolution_rule,
            confidence_score,
            resolved_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            resolution_id,
            alias_id,
            entity_id,
            resolution_action,
            match_method,
            confidence_score,
            "SYSTEM",
        ),
    )

    return {
        "created": created,
        "alias_id": alias_id,
        "resolution_id": resolution_id,
    }


def persist_resolutions(conn, resolutions):
    """
    Persist multiple resolution decisions.

    Returns summary statistics.
    """

    created = 0
    existing = 0
    skipped = 0

    for resolution in resolutions:

        result = persist_resolution(
            conn,
            resolution,
        )

        if resolution["resolution_action"] != "MATCHED":
            skipped += 1

        elif result["created"]:
            created += 1

        else:
            existing += 1

    conn.commit()

    return {
        "created": created,
        "existing": existing,
        "skipped": skipped,
        "total": len(resolutions),
    }
