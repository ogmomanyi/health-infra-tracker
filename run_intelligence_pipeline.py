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
    is_non_entity_name,
    load_candidates,
    resolve_source_record,
)
from organisation_resolution import opportunity_group_resolver
from procurement_intelligence.historical_quote_intelligence import load_evidence
from procurement_intelligence.historical_scoring import apply_historical_familiarity
from seed_organisation_groups import seed_groups


builder = importlib.import_module("intelligence_builder")
DB = Path("data/iati_intelligence.db")
HISTORICAL_EVIDENCE = load_evidence(Path("data/faram_historical_quote_evidence.csv"))

REFERENCE_COLUMNS = (
    ("organisation_intelligence", "organisation_entity_id"),
    ("target_accounts", "organisation_entity_id"),
    ("equipment_entities", "organisation_entity_id"),
    ("opportunity_organisation_resolution", "entity_id"),
    ("organisation_resolution_log", "entity_id"),
    ("organisation_manual_overrides", "entity_id"),
    ("organisation_group_members", "entity_id"),
)

DATA_FOUNDATION_SOURCES = {
    "activities": ("iati_health_projects.csv", "activities.csv"),
    "transactions": ("transactions.csv",),
    "organisations": ("organisations.csv",),
    "iati_activities": ("iati_health_projects.csv", "activities.csv"),
    "iati_transactions": ("transactions.csv",),
    "iati_organisations": ("organisations.csv",),
}


def canonical_map():
    if not canonical_registry_ready(DB):
        return {}, {}, {}

    ensure_canonical_compatibility(DB)
    conn = sqlite3.connect(DB)
    by_ref = {}
    by_name = {}
    alias_by_name = {}
    tables = sqlite_tables(DB)
    entity_columns = table_columns(conn, "organisation_entities")
    alias_columns = table_columns(conn, "organisation_aliases")
    entity_id_column = "entity_id" if "entity_id" in entity_columns else "organisation_entity_id"
    alias_entity_id_column = "entity_id" if "entity_id" in alias_columns else "organisation_entity_id"
    has_status = "entity_status" in entity_columns

    parent_by_child = {}

    if "organisation_relationships" in tables:
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


def sync_data_foundation_artifacts(data_dir, db_path, write_sqlite=True):
    data_dir = Path(data_dir)
    counts = {}
    datasets = {}

    for dataset_name, source_names in DATA_FOUNDATION_SOURCES.items():
        dataframe = builder.read_first_available_csv(data_dir, *source_names)

        if dataframe.empty:
            continue

        output_path = data_dir / f"{dataset_name}.csv"
        dataframe.to_csv(output_path, index=False)
        counts[dataset_name] = int(len(dataframe))
        datasets[dataset_name] = dataframe

    if write_sqlite and datasets:
        conn = sqlite3.connect(db_path)
        try:
            for table_name, dataframe in datasets.items():
                dataframe.to_sql(table_name, conn, if_exists="replace", index=False)
            conn.commit()
        finally:
            conn.close()

    if counts:
        sync_manifest_counts(data_dir / "manifest.json", counts)

        raw_counts = {
            name: count for name, count in counts.items() if name.startswith("iati_")
        }
        normalized_counts = {
            name: count for name, count in counts.items() if not name.startswith("iati_")
        }

        if raw_counts:
            sync_summary_counts(data_dir / "market_summary.json", raw_counts, "raw")

        if normalized_counts:
            sync_summary_counts(
                data_dir / "market_summary.json",
                normalized_counts,
                "normalized",
            )

    return counts


def canonical_registry_ready(db_path):
    if not Path(db_path).exists():
        return False

    tables = sqlite_tables(db_path)

    return {
        "organisation_entities",
        "organisation_aliases",
    }.issubset(tables)


def ensure_canonical_compatibility(db_path):
    if not Path(db_path).exists():
        return

    conn = sqlite3.connect(db_path)

    try:
        tables = sqlite_tables(db_path)

        if "organisation_entities" in tables:
            ensure_organisation_entity_columns(conn)

        if "organisation_aliases" in tables:
            ensure_organisation_alias_columns(conn)

        conn.commit()
    finally:
        conn.close()


def ensure_column(conn, table_name, column_name, column_type):
    if column_name in table_columns(conn, table_name):
        return

    conn.execute(
        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
    )


def ensure_organisation_entity_columns(conn):
    ensure_column(conn, "organisation_entities", "organisation_entity_id", "TEXT")
    ensure_column(conn, "organisation_entities", "entity_id", "TEXT")
    ensure_column(conn, "organisation_entities", "organisation_type", "TEXT")
    ensure_column(conn, "organisation_entities", "primary_org_ref", "TEXT")
    ensure_column(conn, "organisation_entities", "org_refs", "TEXT")
    ensure_column(conn, "organisation_entities", "org_types", "TEXT")
    ensure_column(conn, "organisation_entities", "roles", "TEXT")
    ensure_column(conn, "organisation_entities", "activity_count", "INTEGER")
    ensure_column(conn, "organisation_entities", "active_activity_count", "INTEGER")
    ensure_column(conn, "organisation_entities", "pipeline_activity_count", "INTEGER")
    ensure_column(conn, "organisation_entities", "country_codes", "TEXT")
    ensure_column(conn, "organisation_entities", "country_names", "TEXT")
    ensure_column(conn, "organisation_entities", "reported_budget", "REAL")
    ensure_column(conn, "organisation_entities", "average_opportunity_score", "REAL")
    ensure_column(conn, "organisation_entities", "high_priority_opportunities", "INTEGER")
    ensure_column(conn, "organisation_entities", "top_equipment_categories", "TEXT")
    ensure_column(conn, "organisation_entities", "latest_update", "TEXT")
    ensure_column(conn, "organisation_entities", "source_layer", "TEXT")
    ensure_column(conn, "organisation_entities", "entity_status", "TEXT")
    ensure_column(conn, "organisation_entities", "updated_at", "TEXT")

    columns = table_columns(conn, "organisation_entities")

    if "organisation_entity_id" in columns and "entity_id" in columns:
        conn.execute(
            """
            UPDATE organisation_entities
            SET entity_id = organisation_entity_id
            WHERE (entity_id IS NULL OR entity_id = '')
              AND organisation_entity_id IS NOT NULL
              AND organisation_entity_id != ''
            """
        )
        conn.execute(
            """
            UPDATE organisation_entities
            SET organisation_entity_id = entity_id
            WHERE (organisation_entity_id IS NULL OR organisation_entity_id = '')
              AND entity_id IS NOT NULL
              AND entity_id != ''
            """
        )

    conn.execute(
        """
        UPDATE organisation_entities
        SET entity_status = 'ACTIVE'
        WHERE entity_status IS NULL OR entity_status = ''
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_organisation_entities_entity_id
        ON organisation_entities(entity_id)
        """
    )


def ensure_organisation_alias_columns(conn):
    ensure_column(conn, "organisation_aliases", "organisation_alias_id", "TEXT")
    ensure_column(conn, "organisation_aliases", "alias_id", "TEXT")
    ensure_column(conn, "organisation_aliases", "organisation_entity_id", "TEXT")
    ensure_column(conn, "organisation_aliases", "entity_id", "TEXT")
    ensure_column(conn, "organisation_aliases", "alias", "TEXT")
    ensure_column(conn, "organisation_aliases", "alias_name", "TEXT")
    ensure_column(conn, "organisation_aliases", "organisation_key", "TEXT")
    ensure_column(conn, "organisation_aliases", "source_system", "TEXT")
    ensure_column(conn, "organisation_aliases", "is_primary_alias", "INTEGER")
    ensure_column(conn, "organisation_aliases", "match_method", "TEXT")
    ensure_column(conn, "organisation_aliases", "confidence_score", "REAL")

    conn.execute(
        """
        UPDATE organisation_aliases
        SET alias_id = organisation_alias_id
        WHERE (alias_id IS NULL OR alias_id = '')
          AND organisation_alias_id IS NOT NULL
          AND organisation_alias_id != ''
        """
    )
    conn.execute(
        """
        UPDATE organisation_aliases
        SET organisation_alias_id = alias_id
        WHERE (organisation_alias_id IS NULL OR organisation_alias_id = '')
          AND alias_id IS NOT NULL
          AND alias_id != ''
        """
    )
    conn.execute(
        """
        UPDATE organisation_aliases
        SET entity_id = organisation_entity_id
        WHERE (entity_id IS NULL OR entity_id = '')
          AND organisation_entity_id IS NOT NULL
          AND organisation_entity_id != ''
        """
    )
    conn.execute(
        """
        UPDATE organisation_aliases
        SET organisation_entity_id = entity_id
        WHERE (organisation_entity_id IS NULL OR organisation_entity_id = '')
          AND entity_id IS NOT NULL
          AND entity_id != ''
        """
    )
    conn.execute(
        """
        UPDATE organisation_aliases
        SET alias_name = alias
        WHERE (alias_name IS NULL OR alias_name = '')
          AND alias IS NOT NULL
          AND alias != ''
        """
    )
    conn.execute(
        """
        UPDATE organisation_aliases
        SET alias = alias_name
        WHERE (alias IS NULL OR alias = '')
          AND alias_name IS NOT NULL
          AND alias_name != ''
        """
    )
    conn.execute(
        """
        UPDATE organisation_aliases
        SET organisation_key = COALESCE(
            NULLIF(org_ref, ''),
            NULLIF(alias, ''),
            NULLIF(alias_name, ''),
            alias_id
        )
        WHERE organisation_key IS NULL OR organisation_key = ''
        """
    )
    conn.execute(
        """
        UPDATE organisation_aliases
        SET source_system = 'IATI'
        WHERE source_system IS NULL OR source_system = ''
        """
    )
    conn.execute(
        """
        UPDATE organisation_aliases
        SET is_primary_alias = 0
        WHERE is_primary_alias IS NULL
        """
    )
    conn.execute(
        """
        UPDATE organisation_aliases
        SET match_method = 'GENERATED_ALIAS'
        WHERE match_method IS NULL OR match_method = ''
        """
    )
    conn.execute(
        """
        UPDATE organisation_aliases
        SET confidence_score = 1.0
        WHERE confidence_score IS NULL
        """
    )


def cleanup_canonical_registry(db_path):
    if not canonical_registry_ready(db_path):
        return

    ensure_canonical_compatibility(db_path)
    conn = sqlite3.connect(db_path)

    try:
        tables = sqlite_tables(db_path)
        remove_non_entity_canonical_records(conn, tables)

        if "organisation_relationships" in tables:
            delete_broken_relationships(conn)

        conn.commit()
    finally:
        conn.close()


def remove_non_entity_canonical_records(conn, tables):
    rows = conn.execute(
        """
        SELECT entity_id, organisation_entity_id, canonical_name
        FROM organisation_entities
        """
    ).fetchall()
    entity_ids = {
        value
        for entity_id, organisation_entity_id, canonical_name in rows
        if is_non_entity_name(canonical_name)
        for value in (entity_id, organisation_entity_id)
        if value
    }

    if not entity_ids:
        return

    placeholders = ",".join("?" for _ in entity_ids)

    if "organisation_aliases" in tables:
        conn.execute(
            f"""
            DELETE FROM organisation_aliases
            WHERE entity_id IN ({placeholders})
               OR organisation_entity_id IN ({placeholders})
            """,
            tuple(entity_ids) + tuple(entity_ids),
        )

    if "organisation_relationships" in tables:
        conn.execute(
            f"""
            DELETE FROM organisation_relationships
            WHERE parent_entity_id IN ({placeholders})
               OR child_entity_id IN ({placeholders})
            """,
            tuple(entity_ids) + tuple(entity_ids),
        )

    for table_name, column_name in REFERENCE_COLUMNS:
        if table_name not in tables or column_name not in table_columns(conn, table_name):
            continue

        conn.execute(
            f"""
            DELETE FROM {table_name}
            WHERE {column_name} IN ({placeholders})
            """,
            tuple(entity_ids),
        )

    conn.execute(
        f"""
        DELETE FROM organisation_entities
        WHERE entity_id IN ({placeholders})
           OR organisation_entity_id IN ({placeholders})
        """,
        tuple(entity_ids) + tuple(entity_ids),
    )

    print(f"[intel] Removed non-entity canonical records ({len(entity_ids)} ids)")


def delete_broken_relationships(conn):
    deleted = conn.execute(
        """
        DELETE FROM organisation_relationships
        WHERE parent_entity_id NOT IN (
            SELECT entity_id FROM organisation_entities
            WHERE entity_id IS NOT NULL AND entity_id != ''
        )
           OR child_entity_id NOT IN (
            SELECT entity_id FROM organisation_entities
            WHERE entity_id IS NOT NULL AND entity_id != ''
        )
        """
    ).rowcount

    if deleted:
        print(f"[intel] Removed broken organisation relationships ({deleted} rows)")


def upsert_missing_canonical_entities(derived):
    if not canonical_registry_ready(DB):
        return

    ensure_canonical_compatibility(DB)
    by_ref, by_name, alias_by_name = canonical_map()
    conn = sqlite3.connect(DB)

    try:
        entity_columns = table_columns(conn, "organisation_entities")
        alias_columns = table_columns(conn, "organisation_aliases")
        entity_ids = existing_values(
            conn,
            "organisation_entities",
            "entity_id",
            entity_columns,
        ) | existing_values(
            conn,
            "organisation_entities",
            "organisation_entity_id",
            entity_columns,
        )
        alias_ids = existing_values(
            conn,
            "organisation_aliases",
            "alias_id",
            alias_columns,
        ) | existing_values(
            conn,
            "organisation_aliases",
            "organisation_alias_id",
            alias_columns,
        )
        inserted_entities = 0
        inserted_aliases = 0

        for _, row in derived.iterrows():
            canonical_name = builder.clean_text(row.get("canonical_name"))

            if is_non_entity_name(canonical_name):
                continue

            if resolve_row(row, by_ref, by_name, alias_by_name):
                continue

            entity_id = builder.clean_text(row.get("organisation_entity_id"))

            if not entity_id or not canonical_name or entity_id in entity_ids:
                continue

            insert_organisation_entity(conn, entity_columns, row, entity_id)
            entity_ids.add(entity_id)
            by_name[normalize_name(canonical_name)] = entity_id
            inserted_entities += 1

            for alias_id in insert_organisation_aliases(conn, alias_columns, row, entity_id, alias_ids):
                alias_ids.add(alias_id)
                inserted_aliases += 1

            for ref in builder.split_values(row.get("org_refs")):
                if ref.strip():
                    by_ref[ref.strip().lower()] = entity_id

            primary_ref = builder.clean_text(row.get("primary_org_ref"))

            if primary_ref:
                by_ref[primary_ref.lower()] = entity_id

        conn.commit()
    finally:
        conn.close()

    if inserted_entities:
        print(
            "[intel] Added missing canonical organisations "
            f"({inserted_entities} entities, {inserted_aliases} aliases)"
        )


def existing_values(conn, table_name, column_name, columns):
    if column_name not in columns:
        return set()

    return {
        value
        for (value,) in conn.execute(
            f"""
            SELECT {column_name}
            FROM {table_name}
            WHERE {column_name} IS NOT NULL AND {column_name} != ''
            """
        )
    }


def insert_organisation_entity(conn, columns, row, entity_id):
    values = {
        "organisation_entity_id": entity_id,
        "entity_id": entity_id,
        "canonical_name": builder.clean_text(row.get("canonical_name")),
        "organisation_type": builder.clean_text(row.get("org_types")),
        "primary_org_ref": builder.clean_text(row.get("primary_org_ref")),
        "org_refs": builder.clean_text(row.get("org_refs")),
        "org_types": builder.clean_text(row.get("org_types")),
        "roles": builder.clean_text(row.get("roles")),
        "activity_count": builder.safe_float(row.get("activity_count")),
        "active_activity_count": builder.safe_float(row.get("active_activity_count")),
        "pipeline_activity_count": builder.safe_float(row.get("pipeline_activity_count")),
        "country_codes": builder.clean_text(row.get("country_codes")),
        "country_names": builder.clean_text(row.get("country_names")),
        "reported_budget": builder.safe_float(row.get("reported_budget")),
        "average_opportunity_score": builder.safe_float(row.get("average_opportunity_score")),
        "high_priority_opportunities": builder.safe_float(row.get("high_priority_opportunities")),
        "top_equipment_categories": builder.clean_text(row.get("top_equipment_categories")),
        "latest_update": builder.clean_text(row.get("latest_update")),
        "entity_status": "ACTIVE",
        "updated_at": "",
        "source_layer": "canonical",
    }
    selected_columns = [column for column in columns if column in values]

    conn.execute(
        f"""
        INSERT INTO organisation_entities ({", ".join(selected_columns)})
        VALUES ({", ".join("?" for _ in selected_columns)})
        """,
        [values[column] for column in selected_columns],
    )


def insert_organisation_aliases(conn, columns, row, entity_id, alias_ids):
    canonical_name = builder.clean_text(row.get("canonical_name"))
    roles = builder.split_values(row.get("roles"))
    role = roles[0] if roles else ""
    refs = list(dict.fromkeys([
        *builder.split_values(row.get("primary_org_ref")),
        *builder.split_values(row.get("org_refs")),
    ]))

    if not refs:
        refs = [""]

    inserted = []

    for ref in refs:
        alias_id = builder.stable_id(
            "org_alias",
            entity_id,
            canonical_name,
            ref,
            role,
        )

        if alias_id in alias_ids:
            continue

        values = {
            "organisation_alias_id": alias_id,
            "alias_id": alias_id,
            "organisation_entity_id": entity_id,
            "entity_id": entity_id,
            "alias": canonical_name,
            "alias_name": canonical_name,
            "org_ref": builder.clean_text(ref),
            "organisation_key": builder.clean_text(ref) or canonical_name,
            "role": role,
            "source_activity_count": builder.safe_float(row.get("activity_count")),
            "source_system": "IATI",
            "is_primary_alias": 0,
            "match_method": "SYSTEM_DISCOVERED",
            "confidence_score": 1.0,
            "source_layer": "canonical",
        }
        selected_columns = [column for column in columns if column in values]

        conn.execute(
            f"""
            INSERT INTO organisation_aliases ({", ".join(selected_columns)})
            VALUES ({", ".join("?" for _ in selected_columns)})
            """,
            [values[column] for column in selected_columns],
        )
        inserted.append(alias_id)

    return inserted


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
    filtered = derived[
        ~derived["canonical_name"].apply(is_non_entity_name)
    ].copy()

    if not canonical_registry_ready(DB):
        return _original_build_org_intel(filtered)

    upsert_missing_canonical_entities(filtered)
    cleanup_canonical_registry(DB)
    by_ref, by_name, alias_by_name = canonical_map()
    fixed = filtered.copy()
    fixed["organisation_entity_id"] = fixed.apply(
        lambda row: resolve_row(row, by_ref, by_name, alias_by_name),
        axis=1,
    )

    unresolved = fixed[fixed["organisation_entity_id"] == ""]
    if not unresolved.empty:
        examples = ", ".join(unresolved["canonical_name"].head(10).tolist())
        raise RuntimeError(
            f"Unresolved canonical organisations after registry sync: "
            f"{len(unresolved)}; examples: {examples}"
        )

    return _original_build_org_intel(fixed)


builder.build_organisation_intelligence = build_org_intel_fixed


_original_build_org_activity_lookup = builder.build_org_activity_lookup


def build_org_activity_lookup_fixed(organisations):
    if not canonical_registry_ready(DB):
        return _original_build_org_activity_lookup(organisations)

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
    generated_view_collisions = {
        name for name in datasets if name in existing_views
    }

    if generated_view_collisions:
        connection = sqlite3.connect(db_path)
        try:
            for name in sorted(generated_view_collisions):
                connection.execute(f'DROP VIEW IF EXISTS "{name}"')
            connection.commit()
        finally:
            connection.close()
        existing_views -= generated_view_collisions

    canonical_tables = (
        {"organisation_entities", "organisation_aliases"}
        if canonical_registry_ready(Path(db_path))
        else set()
    )
    safe_datasets = {
        name: dataframe
        for name, dataframe in datasets.items()
        if name not in {
            *canonical_tables,
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

    ensure_canonical_compatibility(db_path)
    cleanup_canonical_registry(db_path)
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


def sync_summary_counts(path, counts, layer_name="canonical"):
    if not path.exists():
        return

    with path.open("r", encoding="utf-8") as handle:
        summary = json.load(handle)

    canonical = summary.setdefault("layer_counts", {}).setdefault(layer_name, {})
    for name, count in counts.items():
        canonical[name] = count

    with path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)


def rebuild_opportunity_resolution(db_path, data_dir):
    if not canonical_registry_ready(db_path):
        print(f"[intel] WARNING: opportunity resolution database not ready: {db_path}")
        return

    ensure_canonical_compatibility(db_path)
    cleanup_canonical_registry(db_path)
    group_summary = seed_groups(db_path)
    print(
        "[intel] Seeded organisation groups "
        f"({sum(group_summary.values())} memberships)"
    )
    conn = sqlite3.connect(db_path)

    try:
        opportunity_group_resolver.create_resolution_table(conn)
        decisions = opportunity_group_resolver.resolve_opportunity_references(conn)
        opportunity_group_resolver.persist_resolutions(conn, decisions)
    finally:
        conn.close()

    dataframe = read_sqlite_table(db_path, "opportunity_organisation_resolution")
    output_path = data_dir / "opportunity_organisation_resolution.csv"
    dataframe.to_csv(output_path, index=False)
    count = int(len(dataframe))
    print(f"[intel] Saved {output_path} ({count} rows)")

    counts = {"opportunity_organisation_resolution": count}
    sync_manifest_counts(data_dir / "manifest.json", counts)
    sync_summary_counts(data_dir / "market_summary.json", counts, "intelligence")


_original_score_opportunity = builder.score_opportunity


def score_opportunity_with_history(row, as_of):
    base_result = _original_score_opportunity(row, as_of)
    return apply_historical_familiarity(row, base_result, HISTORICAL_EVIDENCE)


builder.score_opportunity = score_opportunity_with_history


def main():
    global DB

    args = builder.parse_args()
    DB = Path(args.database)

    sync_data_foundation_artifacts(
        Path(args.data_dir),
        DB,
        write_sqlite=not args.skip_sqlite,
    )
    ensure_canonical_compatibility(DB)
    cleanup_canonical_registry(DB)

    original_parse_args = builder.parse_args
    builder.parse_args = lambda: args

    try:
        builder.main()
    finally:
        builder.parse_args = original_parse_args

    if not args.skip_sqlite:
        sync_data_foundation_artifacts(Path(args.data_dir), DB)
        rebuild_opportunity_resolution(Path(args.database), Path(args.data_dir))
        sync_canonical_artifacts(Path(args.database), Path(args.data_dir))
    else:
        sync_data_foundation_artifacts(
            Path(args.data_dir),
            DB,
            write_sqlite=False,
        )


if __name__ == "__main__":
    main()
