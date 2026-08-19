import sqlite3
from collections import Counter

from organisation_resolution.database_resolver import resolve_unresolved_records

conn = sqlite3.connect("data/iati_intelligence.db")

results = resolve_unresolved_records(conn)

matched = results["matched"]
unresolved = results["unresolved"]

print("=== ENTITY RESOLUTION HEALTH CHECK ===")
print(f"Source records checked : {len(matched) + len(unresolved)}")
print(f"Matched                : {len(matched)}")
print(f"Unresolved             : {len(unresolved)}")

print()
print("=== MATCH METHODS ===")

methods = Counter(
    r["match_method"]
    for r in matched
)

for method, count in methods.most_common():
    print(f"{method:20} : {count}")

print()
print("=== CONFIDENCE ===")

if matched:
    scores = [
        r["confidence_score"]
        for r in matched
    ]

    print(f"Minimum : {min(scores):.3f}")
    print(f"Maximum : {max(scores):.3f}")
    print(f"Average : {sum(scores) / len(scores):.3f}")

print()
print("=== PLACEHOLDER MATCHES ===")

placeholder_names = {
    "ip not published",
    "undefined",
    "anonymous",
    "unknown",
    "not available",
}

placeholder_matches = [
    r for r in matched
    if r["normalized_name"] in placeholder_names
]

print(f"Placeholder matches : {len(placeholder_matches)}")

for r in placeholder_matches:
    print(
        f"{r['alias_name']} -> "
        f"{r['entity_id']} "
        f"({r['match_method']})"
    )

print()
print("=== UNRESOLVED ===")

if not unresolved:
    print("None")
else:
    for r in unresolved[:20]:
        print(
            f"{r['alias_name']} | "
            f"{r['organisation_key']}"
        )

    if len(unresolved) > 20:
        print(
            f"... and {len(unresolved) - 20} more"
        )

conn.close()
