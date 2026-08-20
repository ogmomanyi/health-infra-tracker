#!/usr/bin/env python3
"""Validate 03D organisation continuity across canonicalisation changes.

The canonical entity layer is allowed to merge or rename source organisations.
A regression therefore must NOT require the old entity ID to remain the
intelligence entity ID. Instead, legacy organisation names must resolve through
current aliases to exactly one current canonical entity, and that entity must
still have current intelligence and target-account coverage.
"""

from __future__ import annotations

import sqlite3
import subprocess
from io import StringIO
from pathlib import Path

import pandas as pd

from organisation_resolution.normalizer import normalize_name

DB = Path("data/iati_intelligence.db")
INTELLIGENCE_CSV = Path("data/organisation_intelligence.csv")
TARGET_ACCOUNTS_CSV = Path("data/target_accounts.csv")


def git_head_csv(path: Path) -> pd.DataFrame:
    result = subprocess.run(
        ["git", "show", f"HEAD:{path.as_posix()}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return pd.read_csv(StringIO(result.stdout))


def load_alias_map(conn: sqlite3.Connection) -> dict[str, set[str]]:
    parents = {
        child: parent
        for parent, child in conn.execute(
            """
            SELECT parent_entity_id, child_entity_id
            FROM organisation_relationships
            WHERE relationship_type = 'DUPLICATE_OF'
            """
        )
    }

    def canonical_id(entity_id: str) -> str:
        seen: set[str] = set()
        current = entity_id
        while current in parents:
            if current in seen:
                raise RuntimeError(
                    f"Cycle detected in DUPLICATE_OF relationships at {current}"
                )
            seen.add(current)
            current = parents[current]
        return current

    alias_map: dict[str, set[str]] = {}
    for alias_name, entity_id in conn.execute(
        """
        SELECT alias_name, entity_id
        FROM organisation_aliases
        WHERE alias_name IS NOT NULL AND alias_name != ''
        """
    ):
        key = normalize_name(alias_name)
        if key:
            alias_map.setdefault(key, set()).add(canonical_id(entity_id))

    for canonical_name, entity_id in conn.execute(
        """
        SELECT canonical_name, entity_id
        FROM organisation_entities
        WHERE entity_status = 'ACTIVE'
        """
    ):
        key = normalize_name(canonical_name)
        if key:
            alias_map.setdefault(key, set()).add(canonical_id(entity_id))

    return alias_map


def resolved_entities(
    names: pd.Series,
    alias_map: dict[str, set[str]],
) -> tuple[set[str], list[tuple[str, list[str]]]]:
    entities: set[str] = set()
    ambiguous: list[tuple[str, list[str]]] = []

    for raw_name in names.dropna():
        name = str(raw_name)
        key = normalize_name(name)
        if not key:
            continue
        candidates = alias_map.get(key, set())
        if len(candidates) == 1:
            entities.add(next(iter(candidates)))
        elif len(candidates) > 1:
            ambiguous.append((name, sorted(candidates)))

    return entities, ambiguous


def main() -> None:
    if not DB.exists():
        raise SystemExit(f"Missing database: {DB}")
    if not INTELLIGENCE_CSV.exists():
        raise SystemExit(f"Missing current intelligence CSV: {INTELLIGENCE_CSV}")

    old = git_head_csv(INTELLIGENCE_CSV)
    current = pd.read_csv(INTELLIGENCE_CSV)

    conn = sqlite3.connect(DB)
    alias_map = load_alias_map(conn)

    current_entities, current_ambiguous = resolved_entities(
        current["organisation_name"], alias_map
    )
    old_entities, old_ambiguous = resolved_entities(
        old["organisation_name"], alias_map
    )

    old_keys = {
        normalize_name(str(value))
        for value in old["organisation_name"].dropna()
        if normalize_name(str(value))
    }
    current_keys = {
        normalize_name(str(value))
        for value in current["organisation_name"].dropna()
        if normalize_name(str(value))
    }

    legacy_only_keys = old_keys - current_keys
    unresolved_legacy = []
    legacy_resolved_entities: set[str] = set()

    for key in sorted(legacy_only_keys):
        candidates = alias_map.get(key, set())
        if len(candidates) == 1:
            entity_id = next(iter(candidates))
            legacy_resolved_entities.add(entity_id)
            if entity_id not in current_entities:
                unresolved_legacy.append((key, entity_id))
        elif not candidates:
            unresolved_legacy.append((key, "UNRESOLVED"))
        else:
            unresolved_legacy.append((key, "AMBIGUOUS: " + ", ".join(sorted(candidates))))

    intelligence_entity_count = conn.execute(
        "SELECT COUNT(DISTINCT organisation_entity_id) FROM organisation_intelligence"
    ).fetchone()[0]
    target_entity_count = conn.execute(
        "SELECT COUNT(DISTINCT organisation_entity_id) FROM target_accounts"
    ).fetchone()[0]

    db_intelligence_entities = {
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT organisation_entity_id FROM organisation_intelligence"
        )
    }
    db_target_entities = {
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT organisation_entity_id FROM target_accounts"
        )
    }

    legacy_missing_intelligence = sorted(legacy_resolved_entities - db_intelligence_entities)
    legacy_missing_targets = sorted(legacy_resolved_entities - db_target_entities)

    conn.close()

    print("=== 03D ORGANISATION REGRESSION ===")
    print(f"OLD intelligence rows:                 {len(old)}")
    print(f"CURRENT intelligence rows:             {len(current)}")
    print(f"OLD normalized names:                  {len(old_keys)}")
    print(f"CURRENT normalized names:              {len(current_keys)}")
    print(f"LEGACY-ONLY normalized names:          {len(legacy_only_keys)}")
    print(f"LEGACY names resolved to canonical IDs: {len(legacy_resolved_entities)}")
    print(f"CURRENT canonical entities in CSV:     {len(current_entities)}")
    print(f"DB intelligence entities:              {intelligence_entity_count}")
    print(f"DB target-account entities:            {target_entity_count}")
    print(f"CURRENT ambiguous names:               {len(current_ambiguous)}")
    print(f"LEGACY ambiguous names:                {len(old_ambiguous)}")
    print(f"LEGACY canonical IDs missing intelligence: {len(legacy_missing_intelligence)}")
    print(f"LEGACY canonical IDs missing targets:      {len(legacy_missing_targets)}")

    failures = []
    if old_ambiguous:
        failures.append("legacy_ambiguous")
    if current_ambiguous:
        failures.append("current_ambiguous")
    if unresolved_legacy:
        failures.append("legacy_unresolved_or_not_current")
    if legacy_missing_intelligence:
        failures.append("legacy_missing_intelligence")
    if legacy_missing_targets:
        failures.append("legacy_missing_targets")

    if unresolved_legacy:
        print("\n=== LEGACY NAMES WITHOUT CURRENT COVERAGE ===")
        for name, entity in unresolved_legacy[:50]:
            print(f"{name} -> {entity}")

    if legacy_missing_intelligence:
        print("\n=== LEGACY ENTITIES MISSING INTELLIGENCE ===")
        for entity in legacy_missing_intelligence:
            print(entity)

    if legacy_missing_targets:
        print("\n=== LEGACY ENTITIES MISSING TARGET ACCOUNTS ===")
        for entity in legacy_missing_targets:
            print(entity)

    if failures:
        raise SystemExit("REGRESSION FAILED: " + ", ".join(failures))

    print("REGRESSION PASSED")
    print(
        "Legacy organisation IDs may change during canonicalisation; continuity "
        "is verified through aliases and canonical entity ownership."
    )


if __name__ == "__main__":
    main()
