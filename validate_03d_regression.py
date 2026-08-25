#!/usr/bin/env python3
"""Validate 03D organisation continuity across canonicalisation changes.

The canonical entity layer is allowed to merge or rename source organisations.
A regression therefore must not require a legacy entity ID or legacy name to
remain present in the current intelligence snapshot when the source no longer
contains that organisation. Continuity is established by resolving every
legacy-only name through current aliases to exactly one canonical entity.

By default the validator compares the current working-tree snapshot with the
previous Git commit (HEAD^). Explicit refs can be supplied when validating a
known-good snapshot against a regenerated snapshot.
"""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
from io import StringIO
from pathlib import Path

import pandas as pd

from organisation_resolution.normalizer import normalize_name

DB = Path("data/iati_intelligence.db")
INTELLIGENCE_CSV = Path("data/organisation_intelligence.csv")
TARGET_ACCOUNTS_CSV = Path("data/target_accounts.csv")


def git_csv(path: Path, ref: str) -> pd.DataFrame:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path.as_posix()}"],
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--old-ref",
        default="HEAD^",
        help="Git ref containing the previous intelligence snapshot (default: HEAD^)",
    )
    parser.add_argument(
        "--new-ref",
        default=None,
        help="Git ref containing the new snapshot; omit to use the working tree",
    )
    return parser.parse_args()


def load_snapshot(path: Path, ref: str | None) -> pd.DataFrame:
    if ref:
        return git_csv(path, ref)
    return pd.read_csv(path)


def main() -> None:
    args = parse_args()

    if not DB.exists():
        raise SystemExit(f"Missing database: {DB}")
    if not INTELLIGENCE_CSV.exists():
        raise SystemExit(f"Missing current intelligence CSV: {INTELLIGENCE_CSV}")
    if not TARGET_ACCOUNTS_CSV.exists():
        raise SystemExit(f"Missing current target-account CSV: {TARGET_ACCOUNTS_CSV}")

    old = load_snapshot(INTELLIGENCE_CSV, args.old_ref)
    current = load_snapshot(INTELLIGENCE_CSV, args.new_ref)
    current_targets = pd.read_csv(TARGET_ACCOUNTS_CSV)

    required = {"organisation_name", "organisation_entity_id"}
    for label, frame in (("old", old), ("current", current)):
        missing = sorted(required - set(frame.columns))
        if missing:
            raise SystemExit(f"{label} snapshot missing required columns: {missing}")

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
    legacy_unresolved = []
    legacy_resolved_entities: set[str] = set()

    for key in sorted(legacy_only_keys):
        candidates = alias_map.get(key, set())
        if len(candidates) == 1:
            legacy_resolved_entities.add(next(iter(candidates)))
        elif not candidates:
            legacy_unresolved.append((key, "UNRESOLVED"))
        else:
            legacy_unresolved.append(
                (key, "AMBIGUOUS: " + ", ".join(sorted(candidates)))
            )

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

    current_csv_entities = set(
        current["organisation_entity_id"].dropna().astype(str)
    )
    current_target_entities = set(
        current_targets["organisation_entity_id"].dropna().astype(str)
    )

    current_missing_intelligence = sorted(
        current_csv_entities - db_intelligence_entities
    )
    current_missing_targets = sorted(
        current_csv_entities - db_target_entities
    )
    target_csv_missing = sorted(
        current_target_entities - db_target_entities
    )

    legacy_not_current = sorted(
        legacy_resolved_entities - current_entities
    )

    conn.close()

    print("=== 03D ORGANISATION REGRESSION ===")
    print(f"OLD snapshot ref:                     {args.old_ref}")
    print(f"CURRENT snapshot ref:                 {args.new_ref or 'WORKTREE'}")
    print(f"OLD intelligence rows:                 {len(old)}")
    print(f"CURRENT intelligence rows:             {len(current)}")
    print(f"OLD normalized names:                  {len(old_keys)}")
    print(f"CURRENT normalized names:              {len(current_keys)}")
    print(f"LEGACY-ONLY normalized names:          {len(legacy_only_keys)}")
    print(f"LEGACY names resolved to canonical IDs: {len(legacy_resolved_entities)}")
    print(f"CURRENT canonical entities in CSV:     {len(current_entities)}")
    print(f"DB intelligence entities:              {len(db_intelligence_entities)}")
    print(f"DB target-account entities:            {len(db_target_entities)}")
    print(f"CURRENT target-account entities:       {len(current_target_entities)}")
    print(f"CURRENT ambiguous names:               {len(current_ambiguous)}")
    print(f"LEGACY ambiguous names:                {len(old_ambiguous)}")
    print(f"LEGACY resolved but absent from current snapshot: {len(legacy_not_current)}")
    print(f"CURRENT entities missing DB intelligence:         {len(current_missing_intelligence)}")
    print(f"CURRENT entities missing DB target accounts:      {len(current_missing_targets)}")
    print(f"CURRENT target rows missing DB target accounts:   {len(target_csv_missing)}")

    failures = []
    if old_ambiguous:
        failures.append("legacy_ambiguous")
    if current_ambiguous:
        failures.append("current_ambiguous")
    if legacy_unresolved:
        failures.append("legacy_unresolved")
    if current_missing_intelligence:
        failures.append("current_missing_intelligence")
    if current_missing_targets:
        failures.append("current_missing_targets")
    if target_csv_missing:
        failures.append("target_csv_missing_db_coverage")

    if legacy_unresolved:
        print("\n=== LEGACY NAMES THAT CANNOT RESOLVE ===")
        for name, entity in legacy_unresolved[:50]:
            print(f"{name} -> {entity}")

    if legacy_not_current:
        print("\n=== LEGACY ENTITIES RETIRED FROM CURRENT SNAPSHOT ===")
        for entity in legacy_not_current:
            print(entity)

    if current_missing_intelligence:
        print("\n=== CURRENT ENTITIES MISSING INTELLIGENCE ===")
        for entity in current_missing_intelligence:
            print(entity)

    if current_missing_targets:
        print("\n=== CURRENT ENTITIES MISSING TARGET ACCOUNTS ===")
        for entity in current_missing_targets:
            print(entity)

    if target_csv_missing:
        print("\n=== CURRENT TARGET CSV ENTITIES MISSING DB COVERAGE ===")
        for entity in target_csv_missing:
            print(entity)

    if failures:
        raise SystemExit("REGRESSION FAILED: " + ", ".join(failures))

    print("REGRESSION PASSED")
    print(
        "Legacy organisation IDs may change and legacy names may leave the "
        "current source snapshot; continuity is verified through aliases, "
        "canonical ownership, and complete coverage for all current entities."
    )


if __name__ == "__main__":
    main()
