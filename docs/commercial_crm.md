# Commercial CRM persistence

The commercial intelligence architecture has a deliberate separation between **derived intelligence** and **operational CRM state**.

## Data ownership

`data/commercial_opportunity_workspace.csv` remains generated intelligence. It contains the canonical `commercial_account_priority_score` inherited from the account-priority layer and may be regenerated at any time.

`data/commercial_crm.db` contains mutable operational state:

- `opportunity_context` — synchronized copy of the generated opportunity context; refreshed safely on every intelligence run.
- `opportunity_state` — CRM status, owner, activity overrides and notes. This is never replaced by a pipeline refresh.
- `activity_log` — calls, meetings, emails and other recorded activities.
- `audit_log` — state changes and activity creation for traceability.
- `commercial_pricing_cases` — the current working copy of each named pricing case.
- `commercial_pricing_case_revisions` — immutable cost and selling-price snapshots created on every save.
- `commercial_pricing_approvals` — append-only approval decisions tied to one exact pricing revision.

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

The local CRM server exposes the execution and opportunity workspaces without changing the intelligence pipeline. The opportunity workspace includes current-input pricing calculations, revision creation, and commercial approve/request-changes/reject decisions.

An approval never applies to a mutable case generally. It references a specific `revision_id` and `revision_number`. Saving an approved case creates a new revision whose approval state is `PENDING`; the prior approved snapshot and decision remain queryable in the approval history.

API routes:

- `GET/POST /api/opportunities/{opportunity_id}/pricing`
- `GET/POST /api/opportunities/{opportunity_id}/pricing/{pricing_case_id}/approvals`

Only a complete case with non-negative gross profit that is not held by a human `NO_BID` decision can be approved. Rejections and change requests remain available so reviewers can record why a draft is not acceptable.

For example, application code can use:

```python
from procurement_intelligence.commercial_crm import update_state, add_activity

update_state("OPP-E1", status="QUALIFIED", assigned_owner="Edward")
add_activity("OPP-E1", "CALL", "Spoke with procurement contact", owner="Edward")
```

Do not write CRM state, pricing inputs, or approval decisions back into generated intelligence CSVs or canonical entity tables.
