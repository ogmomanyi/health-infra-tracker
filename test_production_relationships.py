import sqlite3

from organisation_resolution.database_resolver import get_canonical_entity_id

conn = sqlite3.connect("data/iati_intelligence.db")

relationships = conn.execute("""
    SELECT
        r.parent_entity_id,
        p.canonical_name,
        r.child_entity_id,
        c.canonical_name
    FROM organisation_relationships r
    JOIN organisation_entities p
        ON p.organisation_entity_id = r.parent_entity_id
    JOIN organisation_entities c
        ON c.organisation_entity_id = r.child_entity_id
    WHERE r.relationship_type = 'DUPLICATE_OF'
    ORDER BY p.canonical_name
""").fetchall()

print("=== PRODUCTION RELATIONSHIP CHECK ===")
print(f"Relationships found: {len(relationships)}")
print()

failures = []

for parent_id, parent_name, child_id, child_name in relationships:
    resolved_parent = get_canonical_entity_id(conn, parent_id)
    resolved_child = get_canonical_entity_id(conn, child_id)

    status = "PASS" if resolved_parent == resolved_child == parent_id else "FAIL"

    print(
        f"{status} | "
        f"{child_name} -> {parent_name}"
    )

    if status == "FAIL":
        failures.append(
            (
                parent_id,
                parent_name,
                child_id,
                child_name,
                resolved_parent,
                resolved_child,
            )
        )

print()

if failures:
    print("=== FAILURES ===")
    for failure in failures:
        print(failure)
else:
    print("All DUPLICATE_OF relationships resolve to their canonical parent.")

conn.close()
