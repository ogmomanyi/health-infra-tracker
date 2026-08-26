import sqlite3

from organisation_resolution.normalizer import normalize_name
from organisation_resolution.database_resolver import (
    get_canonical_entity_id,
    load_entity_candidates,
    load_alias_candidates,
)


DB = "data/iati_intelligence.db"


def split_values(value):
    if not value:
        return []

    return [
        item.strip()
        for item in str(value).split(";")
        if item.strip()
    ]


def load_group_aliases(conn):
    """Build normalized entity-name aliases for active organisation groups."""
    aliases = {}

    rows = conn.execute("""
        SELECT
            g.group_id,
            g.group_name,
            e.canonical_name
        FROM organisation_groups g
        JOIN organisation_group_members m
            ON m.group_id = g.group_id
        JOIN organisation_entities e
            ON e.entity_id = m.entity_id
        WHERE g.group_status = 'ACTIVE'
          AND e.entity_status = 'ACTIVE'
    """).fetchall()

    for group_id, group_name, canonical_name in rows:
        key = normalize_name(canonical_name)
        if key:
            aliases.setdefault(key, set()).add((group_id, group_name))

    return aliases


def load_group_keys(conn):
    """Load explicit group-level aliases."""
    rows = conn.execute("""
        SELECT group_id, group_name, canonical_group_key
        FROM organisation_groups
        WHERE group_status = 'ACTIVE'
    """).fetchall()

    aliases = {}
    for group_id, group_name, group_key in rows:
        for value in (group_name, group_key):
            normalized = normalize_name(value)
            if normalized:
                aliases.setdefault(normalized, set()).add((group_id, group_name))

    return aliases


def resolve_entity(conn, value, candidates=None):
    """Resolve a name/alias and then follow semantic duplicate parents."""
    normalized = normalize_name(value)
    if not normalized:
        return None

    if candidates is None:
        candidates = load_entity_candidates(conn) + load_alias_candidates(conn)

    matches = {
        candidate["entity_id"]
        for candidate in candidates
        if candidate["normalized_name"] == normalized
    }

    if len(matches) != 1:
        return None

    return get_canonical_entity_id(conn, next(iter(matches)))


def resolve_group(value, group_aliases, group_keys):
    normalized = normalize_name(value)
    if not normalized:
        return None

    candidates = set(group_aliases.get(normalized, set()))
    candidates.update(group_keys.get(normalized, set()))

    if len(candidates) == 1:
        return next(iter(candidates))

    return None


def classify_non_entity(value):
    normalized = normalize_name(value)
    categories = {
        normalize_name("Developing country-based NGO"),
        normalize_name("Secteur privé du pays bénéficiaire"),
        normalize_name(
            "University, college or other teaching institution, research institute or think-tank"
        ),
        normalize_name("Local Government"),
        normalize_name("Gouvernement central (SUD/EST)"),
    }
    return normalized in categories


def find_group_for_entity(conn, entity_id):
    row = conn.execute("""
        SELECT m.group_id
        FROM organisation_group_members m
        JOIN organisation_groups g ON g.group_id = m.group_id
        WHERE m.entity_id = ?
          AND g.group_status = 'ACTIVE'
        LIMIT 1
    """, (entity_id,)).fetchone()
    return row[0] if row else None


def resolve_reference(
    conn,
    value,
    group_aliases,
    group_keys,
    entity_candidates,
):
    """Resolve one opportunity organisation reference."""
    group = resolve_group(value, group_aliases, group_keys)
    if group:
        group_id, _ = group
        return {
            "entity_id": None,
            "group_id": group_id,
            "resolution_level": "GROUP",
            "confidence_score": 1.0,
            "resolution_method": "GROUP_EXACT",
        }

    entity_id = resolve_entity(conn, value, entity_candidates)
    if entity_id:
        return {
            "entity_id": entity_id,
            "group_id": find_group_for_entity(conn, entity_id),
            "resolution_level": "ENTITY",
            "confidence_score": 1.0,
            "resolution_method": "ENTITY_RESOLUTION",
        }

    if classify_non_entity(value):
        return {
            "entity_id": None,
            "group_id": None,
            "resolution_level": "NON_ENTITY",
            "confidence_score": 1.0,
            "resolution_method": "NON_ENTITY_CLASSIFICATION",
        }

    return {
        "entity_id": None,
        "group_id": None,
        "resolution_level": "UNRESOLVED",
        "confidence_score": 0.0,
        "resolution_method": "UNRESOLVED",
    }


def extract_opportunity_references(row):
    opportunity_id, funding_agencies, implementing_partners, reporting_org_name = row
    references = []

    for name in split_values(funding_agencies):
        references.append({
            "opportunity_id": opportunity_id,
            "organisation_name": name,
            "organisation_role": "FUNDING",
        })

    for name in split_values(implementing_partners):
        references.append({
            "opportunity_id": opportunity_id,
            "organisation_name": name,
            "organisation_role": "IMPLEMENTING",
        })

    reporting = str(reporting_org_name).strip() if reporting_org_name else ""
    if reporting:
        references.append({
            "opportunity_id": opportunity_id,
            "organisation_name": reporting,
            "organisation_role": "REPORTING",
        })

    return references


def load_opportunities(conn):
    return conn.execute("""
        SELECT opportunity_id, funding_agencies, implementing_partners, reporting_org_name
        FROM opportunity_intelligence
        ORDER BY opportunity_id
    """).fetchall()


def create_resolution_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS opportunity_organisation_resolution (
            resolution_id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id TEXT NOT NULL,
            organisation_name TEXT NOT NULL,
            organisation_role TEXT NOT NULL,
            entity_id TEXT,
            group_id TEXT,
            resolution_level TEXT NOT NULL,
            confidence_score REAL NOT NULL DEFAULT 0.0,
            resolution_method TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def resolve_opportunity_references(conn):
    group_aliases = load_group_aliases(conn)
    group_keys = load_group_keys(conn)
    entity_candidates = load_entity_candidates(conn) + load_alias_candidates(conn)
    rows = load_opportunities(conn)
    decisions = []

    for row in rows:
        for reference in extract_opportunity_references(row):
            result = resolve_reference(
                conn,
                reference["organisation_name"],
                group_aliases,
                group_keys,
                entity_candidates,
            )
            decisions.append({
                "opportunity_id": reference["opportunity_id"],
                "organisation_name": reference["organisation_name"],
                "organisation_role": reference["organisation_role"],
                **result,
            })

    return decisions


def persist_resolutions(conn, decisions):
    conn.execute("DELETE FROM opportunity_organisation_resolution")
    conn.executemany("""
        INSERT INTO opportunity_organisation_resolution (
            opportunity_id, organisation_name, organisation_role,
            entity_id, group_id, resolution_level,
            confidence_score, resolution_method
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (
            decision["opportunity_id"],
            decision["organisation_name"],
            decision["organisation_role"],
            decision["entity_id"],
            decision["group_id"],
            decision["resolution_level"],
            decision["confidence_score"],
            decision["resolution_method"],
        )
        for decision in decisions
    ])
    conn.commit()


def main():
    conn = sqlite3.connect(DB)
    try:
        create_resolution_table(conn)
        decisions = resolve_opportunity_references(conn)
        persist_resolutions(conn, decisions)
        print(
            f"Opportunity organisation resolution completed: {len(decisions)} references."
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
