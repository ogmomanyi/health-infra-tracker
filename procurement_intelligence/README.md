# External Procurement Intelligence

Phase 2 is now a multi-source procurement intelligence layer. **UNGM is intentionally out of scope.** It requires access that does not add enough value for Faram at this stage, so this pipeline does not depend on UNGM credentials, API access, supplier exports, login flows, or scraping.

## Architecture

```text
Official procurement sources
        |
        +--> World Bank Procurement API
        +--> Official RSS / feeds (AfDB and other publishers)
        +--> Future direct institutional sources
        |
        v
Normalized procurement events
        |
        v
Evidence-only IATI matching
        |
        v
Faram commercial / product intelligence
        |
        v
SQLite + CSV + dashboard
```

## Current automated connectors

### World Bank

Uses the public Procurement API endpoint `https://search.worldbank.org/api/procnotices` without Faram credentials.

```bash
python -m procurement_intelligence.run --source world_bank --country KE --country UG --country RW
```

### Official RSS feeds

A reusable RSS adapter accepts an official feed URL, avoiding bespoke scraping where the publisher already provides a machine-readable feed.

```bash
python -m procurement_intelligence.run \
  --source rss \
  --feed-url "<official-feed-url>" \
  --feed-name "AfDB"
```

Fixture mode remains available for regression tests:

```bash
python -m procurement_intelligence.run --source fixture
```

## Design principles

- Prefer official APIs, RSS feeds, open datasets and permitted public machine-readable sources.
- Keep source acquisition separate from normalization.
- Give every notice a stable ID for deduplication and future change detection.
- Match procurement notices to IATI projects only where there is meaningful evidence.
- Country and equipment category alone cannot create an IATI match.
- Keep downstream Faram intelligence source-independent.

## Source roadmap

1. World Bank procurement API
2. AfDB procurement feeds/notices
3. WHO direct procurement sources where machine-readable access exists
4. UNICEF direct procurement sources where machine-readable access exists
5. UNOPS / UNDP and other institutional sources
6. Global Fund and major health-funder sources
7. National procurement portals in Faram's target markets
8. Procurement awards and historical winners for competitive intelligence
