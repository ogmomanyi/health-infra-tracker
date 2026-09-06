"""Deterministic supplier entity resolution for procurement awards.

Supplier names are never fuzzy-merged automatically. Canonical entities and
unambiguous aliases are safe matches; everything else remains unresolved for
review. Raw awardee names remain available for auditability.
"""

from __future__ import annotations

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
    # Legal suffixes are useful evidence when present, so they are retained.
    return re.sub(r"\s+", " ", value).strip()


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
