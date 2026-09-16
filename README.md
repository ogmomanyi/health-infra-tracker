# Health Infrastructure Spending Tracker

Commercial intelligence workspace for East Africa health infrastructure funding, equipment demand, donor behaviour, and procurement timing signals.

## Pipeline

The project follows this data flow:

```text
RAW -> NORMALIZED -> CANONICAL -> INTELLIGENCE -> COMMERCIAL -> PREDICTIVE_PRODUCT
```

`iati_tracker.py` fetches and normalizes IATI records. `run_intelligence_pipeline.py` calls `intelligence_builder.py` through the canonical-safe wrapper, scores programmes and donors, predicts tender windows, and generates commercial account/action outputs without replacing the canonical organisation registry. The dashboard reads the generated artifacts directly and opens project rows into granular opportunity, tender, engagement, and CRM-note detail.

The internal dashboard loads the complete commercial workspace. GitHub Pages uses `scripts/build_public_dashboard.py` to publish an allowlisted market-intelligence view without target accounts, recommended actions, engagements, CRM notes, or commercial-layer metadata.

## Main Commands

Build intelligence layers from the current normalized data:

```bash
make intelligence
```

Run tests:

```bash
make test
```

Serve the dashboard locally:

```bash
make serve
```

Then open `http://localhost:8765/`.

On macOS, `start_health_tracker.command` provides a one-step launcher. It verifies
that the selected port is the tracker, falls back to the next available port when
another application is in the way, opens the project workspace, and always uses
the persistent CRM database at `data/commercial_crm.db`.

The local workspace includes:

- `/projects` to review projects and start a follow-up workflow
- `/my-work` for due and overdue actions
- `/opportunity.html?id=...` for the full execution record
- `/intelligence` for the granular intelligence dashboard

Product identification is evidence-led. Exact catalogue models and full product
names are verified, controlled device phrases are reported as evidence-backed
families, and broad clinical terms remain review candidates. Each identification
retains its source, reference, excerpt, method, and confidence.

## Key Outputs

- `data/target_accounts.csv`
- `data/recommended_actions.csv`
- `data/programme_intelligence.csv`
- `data/donor_intelligence.csv`
- `data/equipment_intelligence.csv`
- `data/product_intelligence.csv`
- `data/manufacturer_intelligence.csv`
- `data/tender_predictions.csv`
- `data/market_summary.json`
- `data/iati_intelligence.db`

The dashboard in `index.html` reads those generated files directly.
