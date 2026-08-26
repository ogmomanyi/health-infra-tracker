# Health Infrastructure Spending Tracker Data Pipeline

This project follows a layered data flow:

```text
RAW
iati_activities
iati_transactions
iati_organisations

NORMALIZED
activities
transactions
organisations

CANONICAL
organisation_entities
organisation_aliases
equipment_entities
manufacturer_entities

INTELLIGENCE
opportunity_scores
organisation_intelligence
programme_intelligence
donor_intelligence

COMMERCIAL
target_accounts
engagements
crm_notes
recommended_actions

PREDICTIVE_PRODUCT
equipment_intelligence
tender_predictions
```

## Execution Rules

- RAW preserves source-shaped IATI records before business logic.
- NORMALIZED stores clean activity, transaction, and participant records.
- CANONICAL resolves reusable entities used across programmes and accounts.
- INTELLIGENCE scores and summarizes market, donor, organisation, and programme signals.
- COMMERCIAL converts intelligence into account targeting, engagement, CRM note, and action workflows.
- PREDICTIVE_PRODUCT forecasts equipment/product demand and likely procurement timing.

## Intelligence quality rules

- Donor names are clustered into families (USAID, Gavi, Global Fund, UNICEF, and others) before scoring.
- Amounts used for ranking are converted to USD with a documented fallback FX table. Source currencies stay on the row.
- Equipment demand distinguishes `direct_keyword` evidence from `sector_inferred` demand. Inferred demand never counts as an open tender.
- Tender predictions require a probability, a stage, and either direct equipment language, procurement language, or a dated funding window. `Monitor` is not a predicted window.
- Manufacturer entities are created only from explicit text mentions, not guessed from category.

`iati_tracker.py` owns the source fetch and normalized foundation. Entity-resolution modules own canonical organisation IDs. `run_intelligence_pipeline.py` invokes `intelligence_builder.py` without replacing the canonical organisation registry, excludes unresolved derived-only organisation rows from account outputs, and republishes canonical organisation CSVs from SQLite. Daily CI runs the fetcher, the protected intelligence runner, and the tests.
