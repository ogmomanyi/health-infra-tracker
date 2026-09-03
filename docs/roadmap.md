# Platform Roadmap

This roadmap follows the execution plan used by the pipeline and dashboard.

## 1. Data Foundation

Status: ready.

Implemented through `iati_tracker.py` and the normalized SQLite/CSV outputs:

- IATI activity ingestion
- Activities, budgets, planned disbursements, and transactions
- Countries and organisations

Primary outputs:

- `data/activities.csv`
- `data/transactions.csv`
- `data/budgets.csv`
- `data/planned_disbursements.csv`
- `data/activity_countries.csv`
- `data/organisations.csv`

## 2. Intelligence Foundation

Status: ready.

Implemented through `intelligence_builder.py`:

- Market overview
- Procurement language detection
- Equipment demand signals
- Opportunity identification and scoring

Primary outputs:

- `data/opportunities.csv`
- `data/opportunity_scores.csv`
- `data/programme_intelligence.csv`
- `data/market_summary.json`

## 3. Entity + Relationship Intelligence

Status: ready with canonical guardrails.

Implemented through the organisation resolution tables and the protected intelligence runner:

- Organisation normalization
- Entity resolution
- Duplicate relationship support
- Canonical organisations and aliases
- Organisation groups
- Opportunity-to-organisation resolution
- Donor intelligence

Primary outputs:

- `data/organisation_entities.csv`
- `data/organisation_aliases.csv`
- `data/organisation_intelligence.csv`
- `data/donor_intelligence.csv`
- SQLite tables for relationships, groups, and opportunity organisation resolution

Guardrail:

- `run_intelligence_pipeline.py` keeps SQLite as the source of truth for canonical organisation entities and aliases.
- Derived-only unresolved organisations are excluded from target-account generation until canonical resolution catches up.
- Published canonical CSVs are synced back from SQLite after each intelligence run.

## 4. Commercial Intelligence

Status: ready.

Implemented through generated account and workflow outputs plus the dashboard:

- Commercial opportunity scoring
- Target accounts
- Recommended actions
- Engagement intelligence
- CRM notes
- Project-level detail drill-downs in `index.html`

Primary outputs:

- `data/target_accounts.csv`
- `data/engagements.csv`
- `data/crm_notes.csv`
- `data/recommended_actions.csv`

## 5. Predictive / Product Intelligence

Status: ready as a first production layer.

Implemented through product/equipment demand analytics and tender prediction:

- Equipment/product intelligence
- Tender probability and stage
- Procurement timing windows
- Account prioritisation inputs

Primary outputs:

- `data/equipment_entities.csv`
- `data/manufacturer_entities.csv`
- `data/equipment_intelligence.csv`
- `data/tender_predictions.csv`

### Validation and commercial product matching

Status: implemented, awaiting accumulated external observations for calibration.

- Tender-window predictions are validated against externally observed procurement notices.
- Confirmed IATI-to-notice matches provide validation evidence; possible matches remain signals only.
- Procurement notices are matched to explicit product families using deterministic lexical evidence.
- Explicitly named manufacturers are resolved to canonical manufacturer entities when available.
- Manufacturer fit is never inferred merely from a product category.

Primary outputs:

- `data/tender_prediction_validation.csv`
- `data/procurement_product_matches.csv`

The tender model should not be recalibrated until enough observed notices exist to measure systematic timing and probability-band error.

Next enhancement frontier:

- Add richer product-family aliases and specification-level matching.
- Link product families to Faram's actual principal/distributor catalogue and authorization status.
- Validate manufacturer/product matches against awarded tenders and supplier information where publicly available.
- Refresh the canonical organisation registry before each intelligence build rather than only preserving the current registry.
- Add dashboard views for product family, manufacturer, validation performance, and competitor signals.
