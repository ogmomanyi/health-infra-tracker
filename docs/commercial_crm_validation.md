# Commercial CRM Validation

The persistent CRM layer is intentionally separate from generated intelligence.

## End-to-end boundary

`commercial_account_priority.csv` -> `commercial_action_queue.csv` -> `commercial_opportunity_workspace.csv` -> `commercial_crm.db` -> local HTTP API -> `execution.html`

The API exposes mutable operational state only. The canonical `commercial_account_priority_score` and tier remain owned by the commercial account priority layer.

## Local smoke test

Start the server:

```bash
python commercial_crm_server.py
```

Open:

```text
http://127.0.0.1:8765/execution.html
```

The UI can read the persisted opportunity state and submit lifecycle, owner, next-activity, notes, and activity updates through the API.

## Automated coverage

`tests/test_commercial_crm_server.py` verifies:

- API health and opportunity retrieval
- preservation of canonical priority score through CRM mutations
- lifecycle/owner/next-activity/notes updates
- activity creation and retrieval
- audit trail creation
- 404 handling for unknown opportunities
