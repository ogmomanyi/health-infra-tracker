#!/usr/bin/env python3
"""Run intelligence_builder without violating canonical entity ownership.

The legacy builder still constructs organisation-level derived CSVs, but this
runner maps organisation intelligence/commercial records onto the canonical
entity-resolution IDs, follows DUPLICATE_OF relationships to their parents,
and prevents the builder from replacing canonical entity/alias tables.
"""

import importlib
import json
import sqlite3
from pathlib import Path

from organisation_resolution.normalizer import normalize_name
from organisation_resolution.database_resolver import (
    load_candidates,
    resolve_source_record,
)
from procurement_intelligence.historical_quote_intelligence import load_evidence
from procurement_intelligence.historical_scoring import apply_historical_familiarity


builder = importlib.import_module("intelligence_builder")
DB = Path("data/iati_intelligence.db")
HISTORICAL_EVIDENCE = load_evidence(Path("data/faram_historical_quote_evidence.csv"))


def canonical_map():
    conn = sqlite3.connect(DB)
    by_ref = {}
    by_name = {}
    alias_by_name = {}
    entity_columns = table_columns(conn, "organisation_entities")
    alias_columns = table_columns(conn, "organisation_aliases")
    entity_id_column = "entity_id" if "entity_id" in entity_columns else "organisation_entity_id"
    alias_entity_id_column = "entity_id" if "entity_id" in alias_columns else "organisation_entity_id"
    has_status = "entity_status" in entity_columns

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
                raise RuntimeError(f"Cycle detected in DUPLICATE_OF relationships at {current}")
            seen.add(current)
            current = parent_by_child[current]
        return current

    status_clause = "WHERE e.entity_status = 'ACTIVE'" if has_status else ""

    # Canonical names are authoritative. An alias shared by several entities
    # must not make an otherwise exact canonical name ambiguous.
    for entity_id, canonical_name in conn.execute(
        f"""
        SELECT e.{entity_id_column}, e.canonical_name
        FROM organisation_entities e
        {status_clause}
        """
    ):
        normalized = normalize_name(canonical_name)
        if normalized:
            by_name.setdefault(normalized, set()).add(canonical_id(entity_id))

    for org_ref, entity_id in conn.execute(
        f"""
        SELECT a.org_ref, a.{alias_entity_id_column}
        FROM organisation_aliases a
        JOIN organisation_entities e
            ON e.{entity_id_column} = a.{alias_entity_id_column}
        WHERE a.org_ref IS NOT NULL AND a.org_ref != ''
        {"AND e.entity_status = 'ACTIVE'" if has_status else ""}
        """
    ):
        by_ref.setdefault(org_ref.strip().lower(), set()).add(canonical_id(entity_id))

    for alias_name, entity_id in conn.execute(
        f"""
        SELECT a.alias_name, a.{alias_entity_id_column}
        FROM organisation_aliases a
        JOIN organisation_entities e
            ON e.{entity_id_column} = a.{alias_entity_id_column}
        WHERE a.alias_name IS NOT NULL
          AND TRIM(a.alias_name) != ''
          {"AND e.entity_status = 'ACTIVE'" if has_status else ""}
        """
    ):
        normalized = normalize_name(alias_name)
        if normalized:
            alias_by_name.setdefault(normalized, set()).add(canonical_id(entity_id))

    by_ref = {key: next(iter(values)) for key, values in by_ref.items() if len(values) == 1}
    by_name = {key: next(iter(values)) for key, values in by_name.items() if len(values) == 1}
    alias_by_name = {
        key: next(iter(values))
        for key, values in alias_by_name.items()
        if len(values) == 1
    }

    conn.close()
    return by_ref, by_name, alias_by_name


def table_columns(conn, table_name):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}


def resolve_row(row, by_ref, by_name, alias_by_name):
    for ref in builder.split_values(row.get("primary_org_ref")):
        ref = ref.strip().lower()
        if ref and ref in by_ref:
            return by_ref[ref]

    for ref in builder.split_values(row.get("org_refs")):
        ref = ref.strip().lower()
        if ref and ref in by_ref:
            return by_ref[ref]

    name = normalize_name(row.get("canonical_name", ""))
    if name in by_name:
        return by_name[name]
    return alias_by_name.get(name, "")


_original_build_org_intel = builder.build_organisation_intelligence


def build_org_intel_fixed(derived):
    by_ref, by_name, alias_by_name = canonical_map()
    fixed = derived.copy()
    fixed["organisation_entity_id"] = fixed.apply(
        lambda row: resolve_row(row, by_ref, by_name, alias_by_name),
        axis=1,
    )

    unresolved = fixed[fixed["organisation_entity_id"] == ""]
    if not unresolved.empty:
        examples = ", ".join(unresolved["canonical_name"].head(10).tolist())
        print(
            "[intel] WARNING: "
            f"Unresolved canonical organisations: {len(unresolved)}; "
            f"excluded from organisation/account outputs: {examples}"
        )
        fixed = fixed[fixed["organisation_entity_id"] != ""].copy()

    return _original_build_org_intel(fixed)


builder.build_organisation_intelligence = build_org_intel_fixed


def build_org_activity_lookup_fixed(organisations):
    by_ref, by_name, alias_by_name = canonical_map()
    lookup = {}

    for _, row in organisations.iterrows():
        activity_id = builder.clean_text(row.get("activity_id"))
        if not activity_id:
            continue

        ref = builder.clean_text(row.get("org_ref")).lower()
        name = normalize_name(row.get("org_name", ""))
        entity_id = by_ref.get(ref) or by_name.get(name) or alias_by_name.get(name)

        if entity_id:
            lookup.setdefault(entity_id, [])
            if activity_id not in lookup[entity_id]:
                lookup[entity_id].append(activity_id)

    return lookup


builder.build_org_activity_lookup = build_org_activity_lookup_fixed


_original_write_sqlite_tables = builder.write_sqlite_tables


def write_sqlite_tables_fixed(db_path, datasets):
    existing_views = sqlite_views(db_path)
    safe_datasets = {
        name: dataframe
        for name, dataframe in datasets.items()
        if name not in {
            "organisation_entities",
            "organisation_aliases",
            *existing_views,
        }
    }
    _original_write_sqlite_tables(db_path, safe_datasets)


builder.write_sqlite_tables = write_sqlite_tables_fixed


def sqlite_views(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return {name for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'view'")}
    finally:
        conn.close()


def sqlite_tables(db_path):
    conn = sqlite3.connect(db_path)
    try:
        return {name for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        conn.close()


def read_sqlite_table(db_path, table_name):
    conn = sqlite3.connect(db_path)
    try:
        return builder.pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
    finally:
        conn.close()


def sync_canonical_artifacts(db_path, data_dir):
    if not db_path.exists():
        print(f"[intel] WARNING: canonical database not found: {db_path}")
        return

    tables = sqlite_tables(db_path)
    counts = {}

    for name in ("organisation_entities", "organisation_aliases"):
        if name not in tables:
            print(f"[intel] WARNING: canonical table not found: {name}")
            continue

        dataframe = read_sqlite_table(db_path, name)
        output_path = data_dir / f"{name}.csv"
        dataframe.to_csv(output_path, index=False)
        counts[name] = int(len(dataframe))
        print(f"[intel] Synced canonical {output_path} ({len(dataframe)} rows)")

    if counts:
        sync_manifest_counts(data_dir / "manifest.json", counts)
        sync_summary_counts(data_dir / "market_summary.json", counts)


def sync_manifest_counts(path, counts):
    if not path.exists():
        return

    with path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    row_counts = manifest.setdefault("row_counts", {})
    files = manifest.setdefault("files", {})
    for name, count in counts.items():
        row_counts[name] = count
        files[name] = f"{name}.csv"

    with path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)


def sync_summary_counts(path, counts):
    if not path.exists():
        return

    with path.open("r", encoding="utf-8") as handle:
        summary = json.load(handle)

    canonical = summary.setdefault("layer_counts", {}).setdefault("canonical", {})
    for name, count in counts.items():
        canonical[name] = count

    with path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)


_original_score_opportunity = builder.score_opportunity


def score_opportunity_with_history(row, as_of):
    base_result = _original_score_opportunity(row, as_of)
    return apply_historical_familiarity(row, base_result, HISTORICAL_EVIDENCE)


builder.score_opportunity = score_opportunity_with_history


def main():
    args = builder.parse_args()
    original_parse_args = builder.parse_args
    builder.parse_args = lambda: args

    try:
        builder.main()
    finally:
        builder.parse_args = original_parse_args

    sync_canonical_artifacts(Path(args.database), Path(args.data_dir))


if __name__ == "__main__":
    main()
