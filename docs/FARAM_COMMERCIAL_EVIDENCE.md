# Faram Commercial Evidence

`data/faram_commercial_evidence.csv` is a review queue for internal Faram commercial evidence discovered in Faram's mailbox.

## Evidence policy

- Mailbox evidence can identify a manufacturer, supplier, product, quotation or commercial relationship.
- Mailbox evidence does **not** automatically establish an active principal appointment, current product representation or territory authorization.
- `REVIEW` records must be validated against the underlying quotation, catalogue, agreement, distributor certificate or other authoritative internal document before being copied into `data/faram_product_catalogue.csv`.
- External procurement notices must never populate the Faram catalogue automatically.

## Current first-pass findings

The initial mailbox review surfaced direct commercial correspondence involving Molecular Devices, DiaSys, Labtron, Esco LifeSciences, Erlab, Recare, Silver Lake Research and Ansell. These are intentionally staged as evidence rather than asserted as active Faram principals.

The next ingestion pass should extract product/model-level information from attached quotations and supporting documents, then promote only verified records into the controlled catalogue.
