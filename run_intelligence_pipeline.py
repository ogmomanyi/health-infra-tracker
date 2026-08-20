#!/usr/bin/env python3
"""Run intelligence_builder without violating canonical entity ownership."""

import importlib
import sqlite3
from pathlib import Path

from organisation_resolution.normalizer import normalize_name

builder = importlib.import_module("intelligence_builder")
DB = Path("data/iati_intelligence.db")


def canonical_map():
    conn = sqlite3.connect(DB)
    by_ref = {}
    by_name = {}
    parent_by_child = {
        child: parent
        for parent, child in conn.execute(
            """
            SELECT parent_entity_id, child_entity_id
            FROM organisation_relationships
            WHERE relationship_type = 'DUPLICATE_OF'
            """
        )
    }

    def canonical_id(entity_id):
        seen = set()
        current = entity_id
        while current in parent_by_child:
            if current in seen:
                raise RuntimeError(
                    f"Cycle detected in DUPLICATE_OF relationships at {current}"
                )
            seen.add(current)
            current = parent_by_child[current]
        return current

    for entity_id, canonical_name in conn.execute(
        """
        SELECT entity_id, canonical_name
        FROM organisation_entities
        WHERE entity_status = 'ACTIVE'
        """
    ):
        normalized = normalize_name(canonical_name)
        if normalized:
            by_name[normalized] = canonical_id(entity_id)

    for org_ref, entity_id in conn.execute(
        """
        SELECT org_ref, entity_id
        FROM organisation_aliases
        WHERE org_ref IS NOT NULL AND org_ref != ''
        """
    ):
        by_ref[org_ref.strip().lower()] = canonical_id(entity_id)

    conn.close()
    return by_ref, by_name


def resolve_row(row, by_ref, by_name):
    for ref in builder.split_values(row.get("primary_org_ref")):
        ref = ref.strip().lower()
        if ref and ref in by_ref:
            return by_ref[ref]

    for ref in builder.split_values(row.get("org_refs")):
        ref = ref.strip().lower()
        if ref and ref in by_ref:
            return by_ref[ref]

    normalized_name = normalize_name(row.get("canonical_name", ""))
    if normalized_name:
        return by_name.get(normalized_name, "")

    return ""


_original_build_org_intel = builder.build_organisation_intelligence


def build_org_intel_fixed(derived):
    by_ref, by_name = canonical_map()
    fixed = derived.copy()

    # IATI occasionally contains placeholder organisation names such as "-".
    # They are useful as source records but are not canonical organisations.
    # Drop them only when they also have no resolvable org reference; real
    # organisations must still fail loudly if entity resolution cannot map them.
    def has_resolvable_reference(row):
        refs = []
        refs.extend(builder.split_values(row.get("primary_org_ref")))
        refs.extend(builder.split_values(row.get("org_refs")))
        return any(
            ref.strip().lower() in by_ref
            for ref in refs
            if ref.strip()
        )

    placeholder_mask = fixed["canonical_name"].apply(
        lambda value: not normalize_name(value)
    )
    placeholder_without_ref = placeholder_mask & ~fixed.apply(
        has_resolvable_reference,
        axis=1,
    )
    dropped = int(placeholder_without_ref.sum())
    if dropped:
        fixed = fixed.loc[~placeholder_without_ref].copy()

    fixed["organisation_entity_id"] = fixed.apply(
        lambda row: resolve_row(row, by_ref, by_name),
        axis=1,
    )

    unresolved = fixed[fixed["organisation_entity_id"] == ""]
    if not unresolved.empty:
        examples = ", ".join(unresolved["canonical_name"].head(10).tolist())
        raise RuntimeError(
            f"Unresolved canonical organisations: {len(unresolved)}; examples: {examples}"
        )

    if dropped:
        print(f"Ignored {dropped} non-canonical placeholder organisation record(s)")

    return _original_build_org_intel(fixed)


builder.build_organisation_intelligence = build_org_intel_fixed


def build_org_activity_lookup_fixed(organisations):
    by_ref, by_name = canonical_map()
    lookup = {}

    for _, row in organisations.iterrows():
        activity_id = builder.clean_text(row.get("activity_id"))
        if not activity_id:
            continue

        ref = builder.clean_text(row.get("org_ref")).lower()
        name = normalize_name(row.get("org_name", ""))
        entity_id = by_ref.get(ref) or by_name.get(name)

        if entity_id:
            lookup.setdefault(entity_id, [])
            if activity_id not in lookup[entity_id]:
                lookup[entity_id].append(activity_id)

    return lookup


builder.build_org_activity_lookup = build_org_activity_lookup_fixed


_original_write_sqlite_tables = builder.write_sqlite_tables


def write_sqlite_tables_fixed(db_path, datasets):
    safe_datasets = {
        name: dataframe
        for name, dataframe in datasets.items()
        if name not in {"organisation_entities", "organisation_aliases"}
    }
    _original_write_sqlite_tables(db_path, safe_datasets)


builder.write_sqlite_tables = write_sqlite_tables_fixed


if __name__ == "__main__":
    builder.main()
