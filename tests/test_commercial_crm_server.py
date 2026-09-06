import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from commercial_crm_server import CRMHandler
from procurement_intelligence import commercial_crm


def request(server, method, path, payload=None):
    url = f"http://127.0.0.1:{server.server_port}{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_api_state_activity_and_audit(tmp_path):
    db = tmp_path / "crm.db"
    commercial_crm.sync_opportunities(
        [{
            "opportunity_id": "OPP-API-1",
            "target_account_id": "ACC-1",
            "account_name": "API Test Account",
            "country": "Kenya",
            "commercial_account_priority_score": "82",
            "commercial_account_priority_tier": "ACT_NOW",
            "action_category": "QUALIFY_AND_BID",
            "action_status": "OPEN",
            "next_activity": "Qualify buyer",
        }],
        db,
    )
    CRMHandler.db_path = db
    server = ThreadingHTTPServer(("127.0.0.1", 0), CRMHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, health = request(server, "GET", "/api/health")
        assert status == 200 and health == {"ok": True}

        status, item = request(server, "GET", "/api/opportunities/OPP-API-1")
        assert status == 200
        assert item["commercial_account_priority_score"] == 82.0
        assert item["status"] == "OPEN"

        status, item = request(
            server,
            "PATCH",
            "/api/opportunities/OPP-API-1",
            {"status": "QUALIFIED", "assigned_owner": "Edward", "notes": "Qualified by phone", "actor": "test"},
        )
        assert status == 200
        assert item["status"] == "QUALIFIED"
        assert item["assigned_owner"] == "Edward"
        assert item["commercial_account_priority_score"] == 82.0

        status, created = request(
            server,
            "POST",
            "/api/opportunities/OPP-API-1/activities",
            {"activity_type": "CALL", "subject": "Buyer call", "notes": "Discussed tender", "actor": "test"},
        )
        assert status == 201
        assert created["activity_id"] > 0

        status, activities = request(server, "GET", "/api/opportunities/OPP-API-1/activities")
        assert status == 200
        assert activities[0]["subject"] == "Buyer call"

        status, audit = request(server, "GET", "/api/opportunities/OPP-API-1/audit")
        assert status == 200
        assert any(row["change_type"] == "STATE_CHANGE" for row in audit)
        assert any(row["change_type"] == "ACTIVITY_ADDED" for row in audit)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
