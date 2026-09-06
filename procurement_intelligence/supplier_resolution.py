"""Deterministic supplier entity resolution for procurement awards.

Supplier names are never fuzzy-merged automatically. Canonical entities and
unambiguous aliases are safe matches; everything else remains unresolved for
review. Raw awardee names remain available for auditability.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from organisation_resolution.normalizer import normalize_name


@dataclass(frozen=True)
class SupplierResolution:
    raw_name: str
    supplier_country: str
    entity_id: str | None
    canonical_name: str | None
    match_method: str
    confidence_score: float


def supplier_key(name: str) -> str:
    """Normalize a supplier name for deterministic comparison."""
    value = normalize_name(name)
    return re.sub(r"\s+", " ", value).strip()


def supplier_entity_id(normalized_name: str) -> str:
    """Return a stable identifier for a normalized supplier name."""
    digest = hashlib.sha1(normalized_name.encode("utf-8")).hexdigest()[:16]
    return f"SUP-{digest}"


def ensure_supplier_registry(conn: sqlite3.Connection) -> None:
    """Ensure the supplier registry tables exist without destroying data."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS supplier_entities (
            entity_id TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL UNIQUE,
            supplier_type TEXT,
            country TEXT,
            entity_status TEXT DEFAULT 'ACTIVE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_supplier_entity_status
        ON supplier_entities(entity_status);
        CREATE INDEX IF NOT EXISTS idx_supplier_entity_country
        ON supplier_entities(country);
        CREATE TABLE IF NOT EXISTS supplier_aliases (
            alias_id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL,
            alias_name TEXT NOT NULL,
            supplier_country TEXT,
            source_system TEXT NOT NULL DEFAULT 'PROCUREMENT',
            is_primary_alias INTEGER DEFAULT 0,
            match_method TEXT NOT NULL,
            confidence_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (entity_id) REFERENCES supplier_entities(entity_id)
        );
        CREATE INDEX IF NOT EXISTS idx_supplier_alias_entity
        ON supplier_aliases(entity_id);
        CREATE INDEX IF NOT EXISTS idx_supplier_alias_name
        ON supplier_aliases(alias_name);
        """
    )


def seed_explicit_suppliers(conn: sqlite3.Connection, supplier_names: Iterable[tuple[str, str]]) -> int:
    """Register previously unseen explicit awardees without merging variants."""
    inserted = 0
    for raw_name, country in supplier_names:
        normalized = supplier_key(raw_name)
        if not normalized:
            continue
        entity_id = supplier_entity_id(normalized)
        try:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO supplier_entities
                    (entity_id, canonical_name, supplier_type, country)
                VALUES (?, ?, 'COMPANY', ?)
                """,
                (entity_id, raw_name.strip(), country.strip()),
            )
            inserted += cursor.rowcount
        except sqlite3.IntegrityError:
            # A different existing canonical record owns this exact display name.
            # Do not overwrite or merge it automatically.
            continue
    conn.commit()
    return inserted


def load_supplier_candidates(conn: sqlite3.Connection) -> list[dict[str, str]]:
    """Load active canonical suppliers and only unambiguous aliases."""
    rows = conn.execute(
        """
        SELECT entity_id, canonical_name
        FROM supplier_entities
        WHERE entity_status = 'ACTIVE'
        ORDER BY entity_id
        """
    ).fetchall()
    candidates = [
        {
            "entity_id": entity_id,
            "canonical_name": canonical_name,
            "normalized_name": supplier_key(canonical_name),
        }
        for entity_id, canonical_name in rows
    ]

    aliases: dict[str, set[str]] = defaultdict(set)
    for alias_name, entity_id in conn.execute(
        "SELECT alias_name, entity_id FROM supplier_aliases"
    ):
        normalized = supplier_key(alias_name)
        if normalized:
            aliases[normalized].add(entity_id)

    existing = {(row["entity_id"], row["normalized_name"]) for row in candidates}
    canonical_by_entity = {row["entity_id"]: row["canonical_name"] for row in candidates}
    for normalized, entity_ids in aliases.items():
        if len(entity_ids) != 1:
            continue
        entity_id = next(iter(entity_ids))
        key = (entity_id, normalized)
        if key not in existing:
            candidates.append({
                "entity_id": entity_id,
                "canonical_name": canonical_by_entity[entity_id],
                "normalized_name": normalized,
            })
    return candidates


def resolve_supplier(
    raw_name: str,
    supplier_country: str = "",
    candidates: Iterable[dict[str, str]] = (),
) -> SupplierResolution:
    """Resolve by exact canonical/alias normalized name only."""
    normalized = supplier_key(raw_name)
    if not normalized:
        return SupplierResolution(raw_name, supplier_country, None, None, "BLANK", 0.0)

    matches = [c for c in candidates if c["normalized_name"] == normalized]
    entity_ids = {c["entity_id"] for c in matches}
    if len(entity_ids) != 1:
        return SupplierResolution(raw_name, supplier_country, None, None, "UNRESOLVED", 0.0)

    entity_id = next(iter(entity_ids))
    canonical = next(c["canonical_name"] for c in matches if c["entity_id"] == entity_id)
    method = "CANONICAL_EXACT" if normalized == supplier_key(canonical) else "ALIAS_EXACT"
    return SupplierResolution(raw_name, supplier_country, entity_id, canonical, method, 1.0)
