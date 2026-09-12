import csv
from pathlib import Path
import sqlite3
import tempfile
import unittest

from procurement_intelligence.notice_ledger import export_notice_ledger, update_notice_ledger


class NoticeLedgerTests(unittest.TestCase):
    def test_unchanged_observation_is_not_a_new_release_but_amendment_is(self):
        first = {
            "procurement_event_id": "E1", "source": "UNDP",
            "source_record_id": "UNDP-KEN-1", "tender_reference": "UNDP-KEN-1",
            "title": "Supply of analyzer", "closing_date": "2026-09-20",
        }
        amended = {**first, "title": "Supply of analyzer - amended", "closing_date": "2026-09-25"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); database = root / "test.db"
            self.assertEqual(update_notice_ledger(database, [first], observed_at="2026-09-01T00:00:00+00:00")[1], 1)
            self.assertEqual(update_notice_ledger(database, [first], observed_at="2026-09-02T00:00:00+00:00")[1], 0)
            self.assertEqual(update_notice_ledger(database, [amended], observed_at="2026-09-03T00:00:00+00:00")[1], 1)
            totals = export_notice_ledger(database, root)
            self.assertEqual(totals, {"processes": 1, "releases": 2, "documents": 0})
            with (root / "procurement_processes.csv").open(newline="", encoding="utf-8") as handle:
                process = next(csv.DictReader(handle))
            self.assertEqual(process["release_count"], "2")
            self.assertEqual(process["title"], "Supply of analyzer - amended")
            conn = sqlite3.connect(database)
            try:
                current = conn.execute(
                    "SELECT COUNT(*) FROM procurement_releases WHERE is_current = 1"
                ).fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(current, 1)

    def test_known_listing_navigation_is_not_retained_as_a_document(self):
        event = {
            "procurement_event_id": "E1", "source": "UNDP",
            "source_record_id": "UNDP-KEN-1", "title": "Supply of analyzer",
            "document_urls": '["https://procurement-notices.undp.org/search.cfm"]',
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); database = root / "test.db"
            update_notice_ledger(database, [event], observed_at="2026-09-01T00:00:00+00:00")
            totals = export_notice_ledger(database, root)
            self.assertEqual(totals["documents"], 0)
