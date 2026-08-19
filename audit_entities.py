import sqlite3
from collections import Counter

conn = sqlite3.connect("data/iati_intelligence.db")

print("=== ENTITY QUALITY AUDIT ===")

entities = conn.execute("""
    SELECT COUNT(*)
    FROM organisation_entities
    WHERE entity_status = 'ACTIVE'
""").fetchone()[0]

aliases = conn.execute("""
    SELECT COUNT(*)
    FROM organisation_aliases
""").fetchone()[0]

print(f"Active entities : {entities}")
print(f"Total aliases   : {aliases}")

print()
print("=== ENTITIES WITH MOST ALIASES ===")

rows = conn.execute("""
    SELECT
        e.entity_id,
        e.canonical_name,
        COUNT(a.alias_id) AS alias_count
    FROM organisation_entities e
    LEFT JOIN organisation_aliases a
        ON e.entity_id = a.entity_id
    WHERE e.entity_status = 'ACTIVE'
    GROUP BY e.entity_id, e.canonical_name
    HAVING COUNT(a.alias_id) > 1
    ORDER BY alias_count DESC
    LIMIT 15
""").fetchall()

for entity_id, name, count in rows:
    print(f"{count:3} | {name} | {entity_id}")

print()
print("=== GENERIC / POTENTIALLY DANGEROUS NAMES ===")

generic_terms = (
    "ministry of health",
    "ministry of finance",
    "ministry of foreign affairs",
    "university",
    "government",
    "republic of",
    "anonymous",
    "undefined",
    "ip not published",
)

rows = conn.execute("""
    SELECT entity_id, canonical_name
    FROM organisation_entities
    WHERE entity_status = 'ACTIVE'
    ORDER BY canonical_name
""").fetchall()

for entity_id, name in rows:
    if any(term in name for term in generic_terms):
        print(f"{name} | {entity_id}")

print()
print("=== DUPLICATE CANONICAL NAMES ===")

rows = conn.execute("""
    SELECT
        canonical_name,
        COUNT(*) AS entity_count
    FROM organisation_entities
    WHERE entity_status = 'ACTIVE'
    GROUP BY canonical_name
    HAVING COUNT(*) > 1
    ORDER BY entity_count DESC
""").fetchall()

if not rows:
    print("None")
else:
    for name, count in rows:
        print(f"{count:3} | {name}")

print()
print("=== PLACEHOLDER ENTITIES ===")

rows = conn.execute("""
    SELECT entity_id, canonical_name
    FROM organisation_entities
    WHERE LOWER(canonical_name) IN (
        'anonymous',
        'undefined',
        'ip not published',
        'unknown',
        'not available'
    )
    ORDER BY canonical_name
""").fetchall()

if not rows:
    print("None")
else:
    for entity_id, name in rows:
        print(f"{name} | {entity_id}")

conn.close()
