# Commercial CRM persistence

The commercial intelligence architecture has a deliberate separation between **derived intelligence** and **operational CRM state**.

## Data ownership

`data/commercial_opportunity_workspace.csv` remains generated intelligence. It contains the canonical `commercial_account_priority_score` inherited from the account-priority layer and may be regenerated at any time.

`data/commercial_crm.db` contains mutable operational state:

- `opportunity_context` — synchronized copy of the generated opportunity context; refreshed safely on every intelligence run.
- `opportunity_state` — CRM status, owner, activity overrides and notes. This is never replaced by a pipeline refresh.
- `activity_log` — calls, meetings, emails and other recorded activities.
- `audit_log` — state changes and activity creation for traceability.

## Opportunity lifecycle

Supported statuses are:

`OPEN` → `QUALIFIED` → `BID_NO_BID` → `SUBMITTED` → `WON` / `LOST`, with `ON_HOLD` available at any stage.

The module does not calculate or modify commercial priority. Priority is read from the canonical intelligence layer.

## Synchronization

After the intelligence workspace is generated, run:

```bash
python sync_commercial_crm.py
```

This creates the database if needed and upserts opportunity context. Existing CRM state is preserved.

## Local operation

The current execution UI is a static CSV dashboard. The CRM database is intentionally introduced first as the durable operational boundary. A subsequent execution-server layer can expose the database to the UI without changing the intelligence pipeline.

For example, application code can use:

```python
from procurement_intelligence.commercial_crm import update_state, add_activity

update_state("OPP-E1", status="QUALIFIED", assigned_owner="Edward")
add_activity("OPP-E1", "CALL", "Spoke with procurement contact", owner="Edward")
```

Do not write CRM state back into generated intelligence CSVs or into the canonical entity tables.
