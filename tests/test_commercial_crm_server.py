from __future__ import annotations

import json
import csv
import threading
from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory
from http.server import ThreadingHTTPServer

from commercial_crm_server import CRMHandler
from procurement_intelligence import commercial_crm


def _server(db_path: Path, **paths) -> tuple[ThreadingHTTPServer, threading.Thread]:
    handler = type("TestCRMHandler", (CRMHandler,), {"db_path": db_path, **paths})
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
                "procurement_event_id": "EV-TEST-1",
            }
        ],
        db_path,
    )
    return opportunity_id


def test_health_and_get_opportunity():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "crm.db"
        opportunity_id = _seed(db_path)
        server, thread = _server(db_path)
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
            thread.join(timeout=2)


def test_patch_state_and_post_activity():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "crm.db"
        opportunity_id = _seed(db_path)
        server, thread = _server(db_path)
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

            status, activity = _request(
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
            assert isinstance(activity["activity_id"], int)

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
            thread.join(timeout=2)


def test_not_found_returns_404():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "crm.db"
        commercial_crm.initialize(db_path)
        server, thread = _server(db_path)
        try:
            status, data = _request(server, "GET", "/api/opportunities/OPP-MISSING")
            assert status == 404
            assert "error" in data
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_decision_guidance_includes_quote_preparation_without_mutating_priority():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "crm.db"
        opportunity_id = _seed(db_path)
        server, thread = _server(db_path)
        try:
            status, data = _request(
                server,
                "GET",
                f"/api/opportunities/{opportunity_id}/decision-guidance",
            )
            assert status == 200
            assert "bid_decision" in data
            assert "commercial_preparation" in data
            assert "quote_preparation" in data
            assert data["quote_preparation"]["canonical_priority_is_unchanged"] is True
            assert data["quote_preparation"]["decision_is_read_only_guidance"] is True

            status, item = _request(
                server,
                "GET",
                f"/api/opportunities/{opportunity_id}",
            )
            assert status == 200
            assert item["commercial_account_priority_score"] == 81.5
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_procurement_evidence_endpoint_returns_line_items_and_releases():
    with TemporaryDirectory() as tmp:
        root = Path(tmp); db_path = root / "crm.db"
        opportunity_id = _seed(db_path)
        events = root / "events.csv"; items = root / "items.csv"; releases = root / "releases.csv"; documents = root / "documents.csv"; relationships = root / "relationships.csv"
        fixtures = [
            (events, ["procurement_event_id", "procurement_process_id", "notice_text"], [{"procurement_event_id": "EV-TEST-1", "procurement_process_id": "P1", "notice_text": "PCR system"}]),
            (items, ["procurement_event_id", "product_family", "match_status"], [{"procurement_event_id": "EV-TEST-1", "product_family": "PCR System", "match_status": "MATCHED_PRODUCT_FAMILY"}]),
            (releases, ["procurement_process_id", "procurement_release_id", "observed_at"], [{"procurement_process_id": "P1", "procurement_release_id": "R1", "observed_at": "2026-09-12"}]),
            (documents, ["procurement_process_id", "document_url"], [{"procurement_process_id": "P1", "document_url": "https://example.test/spec.pdf"}]),
            (relationships, ["procurement_event_ids", "target_account_id", "party_role", "manufacturer_name"], [{"procurement_event_ids": "EV-TEST-1", "target_account_id": "ACCT-1", "party_role": "BUYER", "manufacturer_name": "Acme"}]),
        ]
        for path, fields, rows in fixtures:
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
        server, thread = _server(
            db_path,
            procurement_events_path=events,
            procurement_line_items_path=items,
            procurement_releases_path=releases,
            procurement_documents_path=documents,
            procurement_relationships_path=relationships,
        )
        try:
            status, payload = _request(server, "GET", f"/api/opportunities/{opportunity_id}/procurement-evidence")
            assert status == 200
            assert payload["line_items"][0]["product_family"] == "PCR System"
            assert payload["releases"][0]["procurement_release_id"] == "R1"
            assert payload["documents"][0]["document_url"].endswith("spec.pdf")
            assert payload["manufacturer_relationships"][0]["manufacturer_name"] == "Acme"
            status, payload = _request(server, "GET", "/api/accounts")
            assert status == 200
            assert payload["accounts"][0]["manufacturer_relationships"][0]["manufacturer_name"] == "Acme"
            status, payload = _request(server, "GET", "/api/accounts/ACCT-1/manufacturer-relationships")
            assert status == 200
            assert payload["manufacturer_relationships"][0]["party_role"] == "BUYER"
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)
