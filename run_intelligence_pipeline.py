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
    names_by_id = {}
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
        canonical_entity_id = canonical_id(entity_id)
        names_by_id[canonical_entity_id] = canonical_name
        normalized = normalize_name(canonical_name)
        if normalized:
            by_name[normalized] = canonical_entity_id

    for org_ref, entity_id in conn.execute(
        """
        SELECT org_ref, entity_id
        FROM organisation_aliases
        WHERE org_ref IS NOT NULL AND org_ref != ''
        """
    ):
        by_ref[org_ref.strip().lower()] = canonical_id(entity_id)

    conn.close()
    return by_ref, by_name, names_by_id


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


def _unique_join(values):
    return builder.join_unique(values)


def _numeric(value):
    return builder.safe_float(value)


def collapse_canonical_rows(frame, canonical_names):
    """Collapse derived source-organisation rows to one row per canonical ID.

    The source organisations table can contain several ref/name variants that
    resolve to one canonical entity. Intelligence must therefore be keyed by
    the canonical entity, not by the pre-resolution stable source ID.
    """
    if frame.empty:
        return frame

    rows = []
    numeric_sum = {
        "activity_count",
        "active_activity_count",
        "pipeline_activity_count",
        "reported_budget",
        "high_priority_opportunities",
    }
    union_fields = {
        "org_refs",
        "org_types",
        "roles",
        "country_codes",
        "country_names",
        "top_equipment_categories",
    }

    for entity_id, group in frame.groupby("organisation_entity_id", sort=False):
        row = group.iloc[0].copy()
        row["organisation_entity_id"] = entity_id
        row["canonical_name"] = canonical_names.get(
            entity_id,
            row.get("canonical_name", ""),
        )

        for field in union_fields:
            row[field] = _unique_join(
                value
                for value in group[field].tolist()
                if builder.clean_text(value)
            )

        for field in numeric_sum:
            row[field] = sum(_numeric(value) for value in group[field].tolist())

        refs = [builder.clean_text(v) for v in group["primary_org_ref"].tolist()]
        refs = [v for v in refs if v]
        row["primary_org_ref"] = refs[0] if refs else ""

        weights = [max(0.0, _numeric(v)) for v in group["activity_count"].tolist()]
        scores = [_numeric(v) for v in group["average_opportunity_score"].tolist()]
        if sum(weights) > 0:
            row["average_opportunity_score"] = sum(
                score * weight for score, weight in zip(scores, weights)
            ) / sum(weights)
        else:
            row["average_opportunity_score"] = (
                sum(scores) / len(scores) if scores else 0.0
            )

        updates = [builder.clean_text(v) for v in group["latest_update"].tolist()]
        updates = [v for v in updates if v]
        row["latest_update"] = max(updates) if updates else ""
        rows.append(row)

    return frame.__class__(rows, columns=frame.columns).reset_index(drop=True)


_original_build_org_entities = builder.build_organisation_entities
_original_build_org_intel = builder.build_organisation_intelligence


def _is_placeholder_name(value):
    """Return True for known non-commercial participant placeholders.

    ``normalize_name`` strips punctuation, so a raw IATI value such as ``-``
    normalizes to an empty string and would otherwise evade the placeholder
    filter, later producing an unresolved canonical organisation error.
    """
    raw = builder.clean_text(value).strip().lower()
    normalized = normalize_name(raw)
    placeholder_names = {
        "ip not published",
        "not published",
        "unknown",
        "unspecified organisation",
        "-",
    }
    return raw in placeholder_names or normalized in placeholder_names or not normalized


def build_org_entities_fixed(organisations, opportunities):
    derived = _original_build_org_entities(organisations, opportunities)
    by_ref, by_name, canonical_names = canonical_map()
    fixed = derived.copy()

    def has_resolvable_reference(row):
        refs = []
        refs.extend(builder.split_values(row.get("primary_org_ref")))
        refs.extend(builder.split_values(row.get("org_refs")))
        return any(
            ref.strip().lower() in by_ref
            for ref in refs
            if ref.strip()
        )

    placeholder_mask = fixed["canonical_name"].apply(_is_placeholder_name)
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

    fixed = collapse_canonical_rows(fixed, canonical_names)

    if dropped:
        print(f"Ignored {dropped} non-canonical placeholder organisation record(s)")

    return fixed


def build_org_intel_fixed(derived):
    by_ref, by_name, canonical_names = canonical_map()
    fixed = derived.copy()

    def has_resolvable_reference(row):
        refs = []
        refs.extend(builder.split_values(row.get("primary_org_ref")))
        refs.extend(builder.split_values(row.get("org_refs")))
        return any(
            ref.strip().lower() in by_ref
            for ref in refs
            if ref.strip()
        )

    placeholder_mask = fixed["canonical_name"].apply(_is_placeholder_name)
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

    fixed = collapse_canonical_rows(fixed, canonical_names)

    if dropped:
        print(f"Ignored {dropped} non-canonical placeholder organisation record(s)")

    return _original_build_org_intel(fixed)


builder.build_organisation_entities = build_org_entities_fixed
builder.build_organisation_intelligence = build_org_intel_fixed


def build_org_activity_lookup_fixed(organisations):
    by_ref, by_name, _ = canonical_map()
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
