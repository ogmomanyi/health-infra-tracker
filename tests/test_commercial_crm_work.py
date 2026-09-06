from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from commercial_crm_server import CRMHandler
from procurement_intelligence import commercial_crm


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
    data = json.loads(response.read().decode("utf-8"))
    conn.close()
    return response.status, data


def _seed(db_path: Path):
    rows = []
    for oid, due, score in [
        ("OPP-OVERDUE", "2026-09-05", 90),
        ("OPP-TODAY", "2026-09-06", 80),
        ("OPP-WEEK", "2026-09-10", 70),
        ("OPP-LATER", "2026-10-01", 60),
        ("OPP-UNASSIGNED", "2026-09-08", 75),
    ]:
        rows.append({
            "opportunity_id": oid,
            "account_name": oid,
            "country": "KE",
            "commercial_account_priority_score": score,
            "commercial_account_priority_tier": "ACT_NOW" if score >= 70 else "PRIORITISE",
            "action_category": "QUALIFY_AND_BID",
            "next_activity": "Contact buyer",
            "next_activity_due_date": due,
        })
    commercial_crm.sync_opportunities(rows, db_path)
    for oid in ("OPP-OVERDUE", "OPP-TODAY"):
        commercial_crm.update_state(oid, db_path=db_path, assigned_owner="Edward")
    commercial_crm.update_state("OPP-WEEK", db_path=db_path, assigned_owner="Grace")
    commercial_crm.update_state("OPP-LATER", db_path=db_path, assigned_owner="Grace")


def test_work_buckets_and_owner_filter():
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "crm.db"
        _seed(db)
        work = commercial_crm.list_opportunities(db)
        assert len(work) == 5
        from procurement_intelligence import commercial_work
        queue = commercial_work.list_work(db, today="2026-09-06")
        assert queue["summary"] == {"active": 5, "overdue": 1, "today": 1, "week": 2, "unassigned": 1}
        buckets = {row["opportunity_id"]: row["work_bucket"] for row in queue["items"]}
        assert buckets["OPP-OVERDUE"] == "overdue"
        assert buckets["OPP-TODAY"] == "today"
        assert buckets["OPP-WEEK"] == "week"
        assert buckets["OPP-LATER"] == "later"
        assert buckets["OPP-UNASSIGNED"] == "week"
        mine = commercial_work.list_work(db, owner="Edward", today="2026-09-06")
        assert {row["opportunity_id"] for row in mine["items"]} == {"OPP-OVERDUE", "OPP-TODAY"}


def test_work_api_returns_summary_and_canonical_score():
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "crm.db"
        _seed(db)
        server, thread = _server(db)
        try:
            status, data = _get(server, "/api/work?today=2026-09-06")
            assert status == 200
            assert data["summary"]["overdue"] == 1
            row = next(x for x in data["items"] if x["opportunity_id"] == "OPP-OVERDUE")
            assert row["commercial_account_priority_score"] == 90.0
            assert row["effective_next_activity"] == "Contact buyer"
            status, mine = _get(server, "/api/work?owner=Edward&today=2026-09-06")
            assert status == 200
            assert {x["opportunity_id"] for x in mine["items"]} == {"OPP-OVERDUE", "OPP-TODAY"}
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
