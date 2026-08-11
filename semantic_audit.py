import sqlite3
from collections import defaultdict

conn = sqlite3.connect("data/iati_intelligence.db")

print("=== SEMANTIC ENTITY AUDIT ===")

# --------------------------------------------------
# 1. Potential duplicates based on removing
#    geographic qualifiers and common prefixes
# --------------------------------------------------

rows = conn.execute("""
    SELECT entity_id, canonical_name
    FROM organisation_entities
    WHERE entity_status = 'ACTIVE'
    ORDER BY canonical_name
""").fetchall()

entities = [
    {
        "entity_id": entity_id,
        "name": canonical_name,
    }
    for entity_id, canonical_name in rows
]

# Conservative transformations.
# These are ONLY for candidate generation.
def candidate_key(name):
    value = name.lower().strip()

    removable = [
        "the ",
    ]

    for prefix in removable:
        if value.startswith(prefix):
            value = value[len(prefix):]

    return value


groups = defaultdict(list)

for entity in entities:
    groups[candidate_key(entity["name"])].append(entity)

potential = [
    group
    for group in groups.values()
    if len(group) > 1
]

print(f"Active entities              : {len(entities)}")
print(f"Potential semantic duplicate groups: {len(potential)}")

print()
print("=== TOP POTENTIAL DUPLICATES ===")

for group in sorted(
    potential,
    key=lambda g: (-len(g), g[0]["name"])
)[:50]:

    print()

    for entity in group:
        print(
            f"{entity['entity_id']} | "
            f"{entity['name']}"
        )

# --------------------------------------------------
# 2. Placeholder entities
# --------------------------------------------------

print()
print("=== PLACEHOLDER ENTITIES ===")

placeholders = conn.execute("""
    SELECT entity_id, canonical_name, entity_status
    FROM organisation_entities
    WHERE LOWER(canonical_name) IN (
        'anonymous',
        'ip not published',
        'undefined',
        'unknown',
        'not available',
        'not disclosed',
        'not specified'
    )
    ORDER BY canonical_name
""").fetchall()

active_placeholders = [
    row for row in placeholders
    if row[2] == 'ACTIVE'
]

inactive_placeholders = [
    row for row in placeholders
    if row[2] == 'INACTIVE'
]

if active_placeholders:
    print("ACTIVE PLACEHOLDERS:")
    for row in active_placeholders:
        print(f"{row[0]} | {row[1]} | {row[2]}")
else:
    print("Active placeholders: 0")

print()

if inactive_placeholders:
    print("INACTIVE PLACEHOLDERS:")
    for row in inactive_placeholders:
        print(f"{row[0]} | {row[1]} | {row[2]}")

print()
print(f"Active placeholders   : {len(active_placeholders)}")
print(f"Inactive placeholders : {len(inactive_placeholders)}")
print(f"Total placeholders    : {len(placeholders)}")

conn.close()
