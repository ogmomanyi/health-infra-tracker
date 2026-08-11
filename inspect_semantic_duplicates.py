import sqlite3

conn = sqlite3.connect("data/iati_intelligence.db")

groups = [
    ("ORG-196E18DB", "ORG-BA66B6F7"),
    ("ORG-81BA5F48", "ORG-35956085"),
    ("ORG-3168C727", "ORG-395981B7"),
    ("ORG-1EC0D518", "ORG-C514FA9E"),
    ("ORG-8007CDFA", "ORG-1DA8CDEF"),
    ("ORG-5C581736", "ORG-FAAB7F05"),
    ("ORG-B93FBED0", "ORG-03F8DA19"),
]

for entity_a, entity_b in groups:
    print()
    print("=" * 70)

    for entity_id in (entity_a, entity_b):
        entity = conn.execute("""
            SELECT entity_id, canonical_name, entity_status
            FROM organisation_entities
            WHERE entity_id = ?
        """, (entity_id,)).fetchone()

        print(f"\nENTITY: {entity}")

        aliases = conn.execute("""
            SELECT alias_id, organisation_key, org_ref,
                   alias_name, match_method
            FROM organisation_aliases
            WHERE entity_id = ?
            ORDER BY alias_name
        """, (entity_id,)).fetchall()

        print("ALIASES:")
        for alias in aliases:
            print(f"  {alias}")

conn.close()
