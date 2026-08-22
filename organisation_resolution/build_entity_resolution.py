#!/usr/bin/env python3
"""Compatibility entry point for the canonical 03D entity resolver.

The old implementation generated random ``ORG-*`` IDs and could therefore
reintroduce a second entity namespace after the 03D repair. The canonical
registry is owned by the repaired/intelligence pipeline; this entry point now
only resolves source aliases against that registry.
"""

import sqlite3

from organisation_resolution.database_resolver import resolve_unresolved_records
from organisation_resolution.database_writer import persist_resolutions

DB_PATH = "data/iati_intelligence.db"


def build_resolution():
    conn = sqlite3.connect(DB_PATH)
    try:
        results = resolve_unresolved_records(conn)
        summary = persist_resolutions(conn, results["matched"])
        print(
            "Canonical entity resolution completed: "
            f"matched={len(results['matched'])}, "
            f"unresolved={len(results['unresolved'])}, "
            f"excluded={len(results['excluded'])}, "
            f"aliases_created={summary['created']}"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    build_resolution()
