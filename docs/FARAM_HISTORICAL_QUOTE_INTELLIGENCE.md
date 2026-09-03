# Faram Historical Quote Intelligence

## Purpose

`data/faram_historical_quote_evidence.csv` records product and manufacturer evidence discovered in Faram mailbox quotation, tender-support and project correspondence.

This dataset is **historical evidence**, not proof of current Faram representation.

## Evidence hierarchy

1. **Current controlled catalogue** — authoritative for current product/principal/territory status.
2. **Historical quotation evidence** — establishes that Faram previously evaluated, requested pricing for, or pursued a product/manufacturer.
3. **External procurement evidence** — establishes market demand, but does not establish Faram capability or representation.
4. **Generic market knowledge** — may support taxonomy only; it must not create a Faram relationship.

## Intended use

Historical evidence should enrich commercial intelligence with:

- products Faram has previously quoted or evaluated
- manufacturers/suppliers with which Faram has engaged
- product families with repeated historical activity
- models previously considered for tenders/projects
- evidence of technical/tender-support relationships

It can be used as a **commercial familiarity signal**, but should not override current principal or territory controls.

## Data quality rules

- Preserve the source email ID whenever available.
- Do not invent missing models, manufacturers or principal status.
- A product mentioned in an external procurement request is not automatically a Faram historical quote.
- Supplier/manufacturer identity comes from the mailbox evidence itself.
- Duplicate email threads should eventually be consolidated into an evidence count rather than repeated catalogue records.
- Old or inactive relationships remain historical unless confirmed by the current Faram catalogue.

## Commercial model

The eventual opportunity score can distinguish:

`CURRENT_CATALOGUE_MATCH` > `HISTORICAL_QUOTE_MATCH` > `PRODUCT_FAMILY_ONLY` > `UNMATCHED`

A historical quote match should increase confidence/familiarity, not automatically make an opportunity actionable.
