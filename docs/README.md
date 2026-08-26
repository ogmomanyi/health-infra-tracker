# Health Infrastructure Spending Tracker

Commercial intelligence workspace for East Africa health infrastructure funding, equipment demand, donor behaviour, and procurement timing signals.

## Pipeline

The project follows this data flow:

```text
RAW -> NORMALIZED -> CANONICAL -> INTELLIGENCE -> COMMERCIAL -> PREDICTIVE_PRODUCT
```

`iati_tracker.py` fetches and normalizes IATI records. `run_intelligence_pipeline.py` calls `intelligence_builder.py` through the canonical-safe wrapper, scores programmes and donors, predicts tender windows, and generates commercial account/action outputs without replacing the canonical organisation registry. The dashboard reads the generated artifacts directly and opens project rows into granular opportunity, tender, engagement, and CRM-note detail.

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

## Key Outputs

- `data/target_accounts.csv`
- `data/recommended_actions.csv`
- `data/programme_intelligence.csv`
- `data/donor_intelligence.csv`
- `data/equipment_intelligence.csv`
- `data/tender_predictions.csv`
- `data/market_summary.json`
- `data/iati_intelligence.db`

The dashboard in `index.html` reads those generated files directly.