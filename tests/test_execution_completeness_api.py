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
            assert snapshot["pricing_cases"] == []
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

            status, pricing = _request(server, "POST", f"/api/opportunities/{opportunity_id}/pricing", {
                "case_name": "Base case",
                "supplier_reference": "SUP-Q-001",
                "supplier_currency": "USD",
                "supplier_cost": 500,
                "pricing_currency": "USD",
                "freight_cost": 50,
                "clearing_and_tax_cost": 25,
                "financing_cost": 10,
                "other_costs": 15,
                "selling_price": 750,
                "cost_basis_complete": True,
                "payment_terms": "50% advance / 50% on delivery",
                "created_by": "Edward",
            })
            assert status == 201
            assert pricing["pricing_status"] == "READY_FOR_COMMERCIAL_APPROVAL"
            assert pricing["total_cost"] == 600.0
            assert pricing["gross_profit"] == 150.0
            assert pricing["margin_pct"] == 20.0
            assert pricing["revision_number"] == 1
            assert pricing["approval_status"] == "PENDING"

            status, approval = _request(
                server,
                "POST",
                f"/api/opportunities/{opportunity_id}/pricing/{pricing['pricing_case_id']}/approvals",
                {
                    "revision_number": pricing["revision_number"],
                    "decision": "APPROVED",
                    "decided_by": "Finance Director",
                    "rationale": "Margin and payment terms accepted.",
                },
            )
            assert status == 201
            assert approval["approval"]["decision"] == "APPROVED"
            assert approval["pricing_case"]["approval_status"] == "APPROVED"

            status, pricing_list = _request(
                server, "GET", f"/api/opportunities/{opportunity_id}/pricing"
            )
            assert status == 200
            assert len(pricing_list["pricing_cases"]) == 1
            assert pricing_list["pricing_cases"][0]["case_name"] == "Base case"
            assert pricing_list["pricing_cases"][0]["approval_status"] == "APPROVED"

            status, approvals = _request(
                server,
                "GET",
                f"/api/opportunities/{opportunity_id}/pricing/{pricing['pricing_case_id']}/approvals",
            )
            assert status == 200
            assert approvals["current_revision_number"] == 1
            assert approvals["approvals"][0]["decided_by"] == "Finance Director"

            status, revised_pricing = _request(
                server,
                "POST",
                f"/api/opportunities/{opportunity_id}/pricing",
                {
                    "pricing_case_id": pricing["pricing_case_id"],
                    "case_name": "Base case",
                    "supplier_reference": "SUP-Q-002",
                    "supplier_currency": "USD",
                    "supplier_cost": 500,
                    "pricing_currency": "USD",
                    "freight_cost": 50,
                    "clearing_and_tax_cost": 25,
                    "financing_cost": 10,
                    "other_costs": 15,
                    "selling_price": 780,
                    "cost_basis_complete": True,
                    "created_by": "Edward",
                },
            )
            assert status == 201
            assert revised_pricing["revision_number"] == 2
            assert revised_pricing["approval_status"] == "PENDING"

            status, stale_approval = _request(
                server,
                "POST",
                f"/api/opportunities/{opportunity_id}/pricing/{pricing['pricing_case_id']}/approvals",
                {
                    "revision_number": 1,
                    "decision": "APPROVED",
                    "decided_by": "Finance Director",
                },
            )
            assert status == 400
            assert "current pricing case revision" in stale_approval["error"]

            status, approvals = _request(
                server,
                "GET",
                f"/api/opportunities/{opportunity_id}/pricing/{pricing['pricing_case_id']}/approvals",
            )
            assert status == 200
            assert approvals["current_revision_number"] == 2
            assert [(row["revision_number"], row["decision"]) for row in approvals["approvals"]] == [
                (1, "APPROVED")
            ]

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
            assert snapshot["pricing_cases"][0]["case_name"] == "Base case"
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

def test_pricing_approval_rejects_incomplete_case_and_missing_reviewer():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "crm.db"
        opportunity_id = _seed(db_path)
        server, thread = _server(db_path)
        try:
            status, pricing = _request(
                server,
                "POST",
                f"/api/opportunities/{opportunity_id}/pricing",
                {
                    "case_name": "Incomplete case",
                    "supplier_currency": "USD",
                    "supplier_cost": 500,
                    "pricing_currency": "USD",
                    "selling_price": 750,
                    "cost_basis_complete": False,
                },
            )
            assert status == 201

            approval_path = (
                f"/api/opportunities/{opportunity_id}/pricing/"
                f"{pricing['pricing_case_id']}/approvals"
            )
            status, error = _request(
                server,
                "POST",
                approval_path,
                {
                    "revision_number": 1,
                    "decision": "APPROVED",
                    "decided_by": "Finance Director",
                },
            )
            assert status == 400
            assert "complete pricing case" in error["error"]

            status, error = _request(
                server,
                "POST",
                approval_path,
                {
                    "revision_number": 1,
                    "decision": "CHANGES_REQUESTED",
                },
            )
            assert status == 400
            assert "reviewer is required" in error["error"]
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

