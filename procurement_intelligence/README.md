# External Procurement Intelligence

## UNGM source policy

UNGM has confirmed that API access is restricted to UN staff. Faram's procurement pipeline therefore does **not** use UNGM API credentials, automated login, or an authenticated API client.

The supplier-facing ingestion path accepts a CSV or JSON feed that Faram is authorized to obtain through UNGM's supplier-facing channels (for example, an alert/export workflow or a locally prepared notice feed).

The ingestion boundary is:

```text
UNGM supplier-facing channel
        |
        v
CSV / JSON feed supplied by Faram
        |
        v
sources/ungm_supplier.py
        |
        v
sources/ungm.py normalization
        |
        v
IATI matching
        |
        v
procurement_events.csv + SQLite
```

No UNGM credentials belong in this repository or in the procurement pipeline.

## Feed format

CSV and JSON are accepted. The minimum useful fields are a title and/or tender reference. The normalizer also understands common aliases such as:

- `title` / `notice_title`
- `tender_reference` / `reference` / `notice_reference` / `noticeId`
- `buyer` / `agency` / `organization` / `organisation`
- `country` / `country_name`
- `publication_date` / `published`
- `closing_date` / `deadline`
- `source_url` / `url` / `notice_url`
- `equipment_category` / `category`
- `product_family` / `product` / `commodity`

Additional fields are preserved through the notice normalization boundary where they are useful to downstream adapters.

## Run

Fixture mode remains available for tests:

```bash
python -m procurement_intelligence.run --source fixture
```

Supplier feed mode:

```bash
python -m procurement_intelligence.run \
  --source supplier \
  --supplier-feed path/to/ungm_export.csv
```

The pipeline then writes the normalized procurement dataset and updates the existing procurement intelligence database layer.
