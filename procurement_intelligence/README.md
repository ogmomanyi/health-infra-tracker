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
Normalized procurement events and detail pages
        |
        +--> stable process IDs + immutable release ledger
        +--> bounded PDF/DOCX/XLSX/HTML text evidence
        |
        v
Evidence-only IATI matching
        |
        +--> multi-item product-family identification
        +--> explicit alias / exact model manufacturer resolution
        |
        v
Faram commercial / product intelligence
        |
        v
SQLite + CSV + dashboard
```

## Current automated connectors

### World Bank

Uses the public Procurement API endpoint `https://search.worldbank.org/api/v2/procnotices` without Faram credentials. Retrieval is paginated and uses bounded retries with backoff.

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

Use `--merge-existing` for a source-specific repair or backfill that must retain records from the other sources.

### UNDP and AfDB

UNDP's current link-row listing and its older table/card layouts are supported. AfDB can use an official RSS feed when configured and otherwise parses the configured official notice pages. A bounded number of health-product detail pages are enriched on each scheduled run.

## Evidence outputs

- `data/procurement_processes.csv` is the current process-level view.
- `data/procurement_releases.csv` retains materially different notice observations.
- `data/procurement_documents.csv` records discovered source documents.
- `data/procurement_document_evidence.csv` records extraction status and bounded text.
- `data/procurement_line_items.csv` contains one-to-many product evidence per notice.
- `data/procurement_manufacturer_relationships.csv` summarizes award and specification affinity for buyers, donors, receiving parties, and target accounts without presenting inferred affinity as stated preference.
- `data/world_bank_project_metadata.csv` caches authoritative borrower and implementing-agency context only for World Bank projects linked to manufacturer-bearing notices.
- `data/procurement_source_collection.csv` records the current scheduled source receipt.
- `data/procurement_source_health.csv` records completeness and matching coverage for CI and operations only.

## Design principles

- Prefer official APIs, RSS feeds, open datasets and permitted public machine-readable sources.
- Keep source acquisition separate from normalization.
- Give every contracting process a stable ID and every material notice version an immutable release ID.
- Match procurement notices to IATI projects only where there is meaningful evidence.
- Country and equipment category alone cannot create an IATI match.
- Keep downstream Faram intelligence source-independent.
- Never infer a manufacturer from a supplier name or a broad product category.
- Treat exact model/product registry matches as identity evidence, not proof of current Faram representation.
- The dashboard module is intentionally separate from the core dashboard page so the procurement UI can evolve without coupling the ingestion pipeline to presentation code.

## Source roadmap

1. World Bank procurement API
2. AfDB procurement feeds/notices
3. WHO direct procurement sources where machine-readable access exists
4. UNICEF direct procurement sources where machine-readable access exists
5. UNOPS and other institutional sources
6. Global Fund and major health-funder sources
7. National procurement portals in Faram's target markets
8. Procurement awards and historical winners for competitive intelligence
