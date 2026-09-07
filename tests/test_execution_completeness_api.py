from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from commercial_crm_server import CRMHandler
from procurement_intelligence import commercial_crm


def _server(db_path: Path) -> tuple[ThreadingHTTPServer, threading.Thread]:
    handler = type("TestCRMHandler", (CRMHandler,), {"db_path": db_path})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _request(server, method, path, payload=None):
    conn = HTTPConnection(*server.server_address, timeout=5)
    body = json.dumps(payload) if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse()
    data = json.loads(response.read().decode("utf-8"))
    conn.close()
    return response.status, data


def _seed(db_path: Path) -> str:
    opportunity_id = "OPP-EXEC-1"
    commercial_crm.sync_opportunities(
        [{
            "opportunity_id": opportunity_id,
            "target_account_id": "ACCT-1",
            "account_name": "Execution Test Hospital",
            "commercial_account_priority_score": "93.0",
            "commercial_account_priority_tier": "ACT_NOW",
            "title": "Analyzer tender",
        }],
        db_path,
    )
    return opportunity_id


def test_execution_completeness_api_lifecycle_preserves_priority():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "crm.db"
        opportunity_id = _seed(db_path)
        server, thread = _server(db_path)
        try:
            status, snapshot = _request(server, "GET", f"/api/opportunities/{opportunity_id}/execution")
            assert status == 200
            assert snapshot["contacts"] == []
            assert snapshot["bid_decision"]["decision"] == "PENDING"
            assert snapshot["outcome"] is None

            status, contact = _request(server, "POST", f"/api/opportunities/{opportunity_id}/contacts", {
                "contact_type": "PROCUREMENT",
                "name": "Jane Buyer",
                "email": "jane@example.org",
                "role": "Procurement Manager",
            })
            assert status == 201
            assert isinstance(contact["contact_id"], int)

            status, decision = _request(server, "POST", f"/api/opportunities/{opportunity_id}/bid-decision", {
                "decision": "BID",
                "decided_by": "Edward",
                "rationale": "Strong fit and credible buyer.",
            })
            assert status == 200
            assert decision["decision"] == "BID"

            status, response = _request(server, "POST", f"/api/opportunities/{opportunity_id}/responses", {
                "response_type": "QUOTE",
                "reference": "Q-001",
                "value": 125000,
                "currency": "USD",
                "status": "SUBMITTED",
            })
            assert status == 201
            assert isinstance(response["response_id"], int)

            status, evidence = _request(server, "POST", f"/api/opportunities/{opportunity_id}/evidence", {
                "evidence_type": "TENDER",
                "title": "Tender notice",
                "location": "https://example.org/tender",
            })
            assert status == 201
            assert isinstance(evidence["evidence_id"], int)

            status, outcome = _request(server, "POST", f"/api/opportunities/{opportunity_id}/outcome", {
                "outcome": "WON",
                "value": 120000,
                "currency": "USD",
                "reason": "Best technical fit",
                "competitor": "Competitor A",
                "lessons": "Early buyer engagement helped.",
                "recorded_by": "Edward",
            })
            assert status == 200
            assert outcome["outcome"] == "WON"

            status, snapshot = _request(server, "GET", f"/api/opportunities/{opportunity_id}/execution")
            assert status == 200
            assert snapshot["contacts"][0]["name"] == "Jane Buyer"
            assert snapshot["bid_decision"]["decision"] == "BID"
            assert snapshot["responses"][0]["reference"] == "Q-001"
            assert snapshot["evidence"][0]["title"] == "Tender notice"
            assert snapshot["outcome"]["outcome"] == "WON"

            status, context = _request(server, "GET", f"/api/opportunities/{opportunity_id}")
            assert status == 200
            assert context["commercial_account_priority_score"] == 93.0
            assert context["commercial_account_priority_tier"] == "ACT_NOW"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_execution_completeness_rejects_unknown_opportunity():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "crm.db"
        commercial_crm.initialize(db_path)
        server, thread = _server(db_path)
        try:
            status, data = _request(server, "GET", "/api/opportunities/OPP-MISSING/execution")
            assert status == 404
            assert "error" in data
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
