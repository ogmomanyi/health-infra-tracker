# External Procurement Intelligence

Phase 2 is a multi-source procurement intelligence layer. UNGM is intentionally out of scope for now: it requires access that does not add enough value to justify making it a dependency for Faram.

## Source strategy

The pipeline separates source retrieval from normalization and commercial intelligence.

```text
Official procurement sources
        |
        +--> World Bank Procurement API
        +--> Development-bank RSS / feeds (e.g. AfDB)
        +--> Future direct institutional sources (WHO, UNICEF, UNOPS, etc.)
        |
        v
Normalized procurement events
        |
        v
Evidence-only IATI matching
        |
        v
Faram opportunity scoring / product intelligence
        |
        v
procurement_events.csv + SQLite + dashboard
```

### Current automated sources

**World Bank** uses the public Procurement API at `https://search.worldbank.org/api/procnotices` and requires no Faram credentials.

**RSS** is a reusable adapter for official procurement feeds. The feed URL is configuration, so individual publishers do not require bespoke ingestion logic unless their feed format requires it.

Example:

```bash
python -m procurement_intelligence.run --source world_bank --country KE --country UG --country RW

python -m procurement_intelligence.run \
  --source rss \
  --feed-url "<official-feed-url>" \
  --feed-name "AfDB"
```

Fixture mode remains available for tests:

```bash
python -m procurement_intelligence.run --source fixture
```

## Design principles

- Prefer official APIs, RSS feeds, open data and machine-readable sources.
- Do not depend on UNGM credentials or authenticated UNGM access.
- Keep source retrieval separate from normalization.
- Give every notice a stable event ID for change detection and deduplication.
- Match procurement notices to IATI projects only when there is textual/evidentiary support; country or equipment category alone is not sufficient.
- Keep the architecture open so additional donor, development-bank, UN-agency and national procurement sources can be added without changing downstream intelligence.

## Planned source order

1. World Bank procurement API
2. AfDB official procurement feed / notices
3. WHO direct procurement sources where available
4. UNICEF direct procurement sources where available
5. UNOPS procurement/eSourcing sources where machine-readable access is available
6. UNDP and other UN-agency sources
7. Global Fund and other major health-funder sources
8. National procurement portals across Faram's target markets
