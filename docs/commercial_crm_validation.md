# Commercial CRM end-to-end validation

The commercial execution flow is intentionally separated into canonical intelligence and mutable CRM state:

`commercial_account_priority.csv` → `commercial_action_queue.csv` → `commercial_opportunity_workspace.csv` → `commercial_crm.db` → local HTTP API → `execution.html`

## Validation coverage

The API integration tests verify:

- health endpoint availability
- opportunity retrieval with the canonical `commercial_account_priority_score`
- lifecycle/status updates
- owner assignment
- next activity and due date updates
- notes persistence
- activity creation and retrieval
- audit records for state and activity changes
- 404 handling for missing opportunities
- preservation of the canonical priority score during CRM mutations

The CRM layer does **not** recalculate commercial priority. Intelligence generation owns the score; the CRM stores and exposes it as read-only context.

## Local smoke test

From the repository root:

```bash
python sync_commercial_crm.py
python commercial_crm_server.py
```

Then open:

`http://127.0.0.1:8765/execution.html`

Run the automated checks with:

```bash
python -m pytest -q
```
