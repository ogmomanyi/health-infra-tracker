import sqlite3
from collections import Counter

from organisation_resolution.normalizer import normalize_name

DB = "data/iati_intelligence.db"


def split_values(value):
    if not value:
        return []

    return [
        item.strip()
        for item in value.split(";")
        if item.strip()
    ]


conn = sqlite3.connect(DB)

try:

    aliases = conn.execute("""
        SELECT
            organisation_key,
            org_ref,
            alias_name,
            entity_id
        FROM organisation_aliases
    """).fetchall()

    by_key = {}
    by_ref = {}
    by_name = {}

    for organisation_key, org_ref, alias_name, entity_id in aliases:

        by_key[organisation_key] = entity_id

        if org_ref:
            by_ref[org_ref] = entity_id

        normalized = normalize_name(alias_name)

        if normalized:
            by_name.setdefault(
                normalized,
                set()
            ).add(entity_id)

    rows = conn.execute("""
        SELECT
            opportunity_id,
            funding_agencies,
            implementing_partners,
            reporting_org_name
        FROM opportunity_intelligence
    """).fetchall()

    unresolved = Counter()
    resolved = 0
    total = 0
    ambiguous = 0

    for opportunity_id, funders, implementers, reporting in rows:

        values = (
            split_values(funders)
            + split_values(implementers)
            + split_values(reporting)
        )

        for value in values:

            total += 1
            entity_id = None

            if value in by_key:
                entity_id = by_key[value]

            elif value in by_ref:
                entity_id = by_ref[value]

            else:
                normalized = normalize_name(value)
                matches = by_name.get(
                    normalized,
                    set()
                )

                if len(matches) == 1:
                    entity_id = next(iter(matches))

                elif len(matches) > 1:
                    ambiguous += 1

            if entity_id:
                resolved += 1
            else:
                unresolved[value] += 1

    print("=== OPPORTUNITY ORGANISATION RESOLUTION ===")
    print(f"Organisation references: {total:,}")
    print(f"Resolved:                {resolved:,}")
    print(f"Unresolved:              {sum(unresolved.values()):,}")
    print(f"Ambiguous:               {ambiguous:,}")

    if total:
        print(
            f"Resolution rate:         "
            f"{resolved / total:.1%}"
        )

    print()
    print("=== UNRESOLVED ORGANISATIONS ===")
    print(
        f"{'OCCURRENCES':>12} | ORGANISATION"
    )
    print("-" * 80)

    for name, count in unresolved.most_common():

        print(
            f"{count:>12} | {name}"
        )

finally:
    conn.close()
