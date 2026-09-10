from __future__ import annotations

import csv
import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from commercial_crm_server import CRMHandler
from procurement_intelligence import commercial_crm, opportunity_technical_fit


def _server(db_path: Path):
    handler = type("TestCRMHandler", (CRMHandler,), {"db_path": db_path})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _get(server, path):
    conn = HTTPConnection(*server.server_address, timeout=5)
    conn.request("GET", path)
    response = conn.getresponse()
    payload = json.loads(response.read().decode("utf-8"))
    conn.close()
    return response.status, payload


def _write_fit(path: Path, event_id: str = "EV-1"):
    fields = [
        "procurement_event_id", "tender_reference", "faram_product_id", "product_name",
        "manufacturer_name", "match_status", "match_confidence", "territory_fit",
        "technical_status", "technical_score", "technical_passed", "technical_unknown",
        "technical_failed", "technical_action",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow({
            "procurement_event_id": event_id, "tender_reference": "T-1", "faram_product_id": "F-1",
            "product_name": "Analyzer A", "manufacturer_name": "Principal A", "match_status": "FARAM_MATCH",
            "match_confidence": "92.0", "territory_fit": "YES", "technical_status": "PASS",
            "technical_score": "100.0", "technical_passed": "8", "technical_unknown": "0",
            "technical_failed": "0", "technical_action": "Proceed to commercial compliance and bid review.",
        })


def _seed(db_path: Path, opportunity_id="OPP-EV-1", event_id="EV-1"):
    commercial_crm.sync_opportunities([{
        "opportunity_id": opportunity_id,
        "procurement_event_id": event_id,
        "account_name": "Test Hospital",
        "commercial_account_priority_score": "88.0",
        "commercial_account_priority_tier": "ACT_NOW",
    }], db_path)


def test_technical_fit_api_returns_generated_rows_for_opportunity():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "crm.db"
        fit_path = root / "faram_product_fit.csv"
        _write_fit(fit_path)
        _seed(db_path)
        server, thread = _server(db_path)
        try:
            status, payload = _get(server, "/api/opportunities/OPP-EV-1/technical-fit")
            assert status == 200
            assert payload["technical_fit"][0]["technical_status"] == "PASS"
            assert payload["technical_fit"][0]["technical_passed"] == "8"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_technical_fit_api_is_empty_for_account_level_opportunity():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "crm.db"
        commercial_crm.sync_opportunities([{
            "opportunity_id": "OPP-ACTION-1", "action_id": "ACTION-1",
            "account_name": "Test Account", "commercial_account_priority_score": "70.0",
            "commercial_account_priority_tier": "DEVELOP",
        }], db_path)
        server, thread = _server(db_path)
        try:
            status, payload = _get(server, "/api/opportunities/OPP-ACTION-1/technical-fit")
            assert status == 200
            assert payload["technical_fit"] == []
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_technical_fit_api_preserves_canonical_priority_context():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "crm.db"
        _seed(db_path)
        server, thread = _server(db_path)
        try:
            status, item = _get(server, "/api/opportunities/OPP-EV-1")
            assert status == 200
            assert item["commercial_account_priority_score"] == 88.0
            assert item["commercial_account_priority_tier"] == "ACT_NOW"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
