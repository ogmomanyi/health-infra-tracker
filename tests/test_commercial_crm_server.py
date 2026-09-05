from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory
from http.server import ThreadingHTTPServer

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
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload)
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse()
    data = json.loads(response.read().decode("utf-8"))
    conn.close()
    return response.status, data


def _seed(db_path: Path) -> str:
    opportunity_id = "OPP-TEST-1"
    commercial_crm.sync_opportunities(
        [
            {
                "opportunity_id": opportunity_id,
                "action_id": "ACTION-1",
                "target_account_id": "ACCT-1",
                "account_name": "Test Hospital",
                "country": "KE",
                "commercial_account_priority_score": "81.5",
                "commercial_account_priority_tier": "ACT_NOW",
                "action_category": "QUALIFY_AND_BID",
                "action_status": "OPEN",
                "next_activity": "Contact buyer",
                "next_activity_due_date": "2026-09-10",
            }
        ],
        db_path,
    )
    return opportunity_id


def test_health_and_get_opportunity():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "crm.db"
        opportunity_id = _seed(db_path)
        server, _ = _server(db_path)
        try:
            status, health = _request(server, "GET", "/api/health")
            assert status == 200
            assert health["ok"] is True

            status, item = _request(server, "GET", f"/api/opportunities/{opportunity_id}")
            assert status == 200
            assert item["commercial_account_priority_score"] == 81.5
            assert item["status"] == "OPEN"
        finally:
            server.shutdown()
            server.server_close()


def test_patch_state_and_post_activity():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "crm.db"
        opportunity_id = _seed(db_path)
        server, _ = _server(db_path)
        try:
            status, item = _request(
                server,
                "PATCH",
                f"/api/opportunities/{opportunity_id}",
                {
                    "status": "QUALIFIED",
                    "assigned_owner": "Edward",
                    "next_activity": "Send tender clarification",
                    "next_activity_due_date": "2026-09-08",
                    "notes": "Priority buyer confirmed.",
                    "actor": "test-user",
                },
            )
            assert status == 200
            assert item["status"] == "QUALIFIED"
            assert item["assigned_owner"] == "Edward"
            assert item["next_activity_override"] == "Send tender clarification"
            assert item["commercial_account_priority_score"] == 81.5

            status, activity_id = _request(
                server,
                "POST",
                f"/api/opportunities/{opportunity_id}/activities",
                {
                    "activity_type": "CALL",
                    "subject": "Buyer call",
                    "notes": "Confirmed technical requirements.",
                    "owner": "Edward",
                    "actor": "test-user",
                },
            )
            assert status == 201
            assert isinstance(activity_id, int)

            status, activities = _request(
                server, "GET", f"/api/opportunities/{opportunity_id}/activities"
            )
            assert status == 200
            assert activities[0]["subject"] == "Buyer call"

            status, audit = _request(
                server, "GET", f"/api/opportunities/{opportunity_id}/audit"
            )
            assert status == 200
            assert any(row["change_type"] == "STATE_CHANGE" for row in audit)
            assert any(row["change_type"] == "ACTIVITY_ADDED" for row in audit)
        finally:
            server.shutdown()
            server.server_close()


def test_not_found_returns_404():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "crm.db"
        commercial_crm.initialize(db_path)
        server, _ = _server(db_path)
        try:
            status, data = _request(server, "GET", "/api/opportunities/OPP-MISSING")
            assert status == 404
            assert "error" in data
        finally:
            server.shutdown()
            server.server_close()
