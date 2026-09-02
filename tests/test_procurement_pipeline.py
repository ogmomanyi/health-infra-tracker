import sqlite3
import tempfile
import unittest
from pathlib import Path

from procurement_intelligence.pipeline import deduplicate_events, persist_events, sync_events
from procurement_intelligence.schema import ProcurementEvent


class ProcurementPipelineTests(unittest.TestCase):
    def test_persist_events_creates_snapshot(self):
        event = ProcurementEvent("proc_1", "World Bank", "https://example.test", "A-1", "Lab equipment", "WHO", "Kenya", "2026-09-01", "2026-10-01", "Laboratory Equipment", "Analyzers")
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            self.assertEqual(persist_events(db, [event]), 1)
            conn = sqlite3.connect(db)
            try:
                count = conn.execute("select count(*) from procurement_intelligence").fetchone()[0]
            finally:
                conn.close()
        self.assertEqual(count, 1)

    def test_deduplicate_events_by_stable_id(self):
        event = ProcurementEvent("proc_1", "World Bank", "", "A-1", "Lab equipment", "WHO", "Kenya", "", "", "Laboratory Equipment", "Analyzers")
        duplicate = ProcurementEvent("proc_1", "World Bank", "", "A-1", "Updated title", "WHO", "Kenya", "", "", "Laboratory Equipment", "Analyzers")
        result = deduplicate_events([event, duplicate])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].title, "Updated title")

    def test_sync_events_round_trips_fixture_csv(self):
        csv_text = """procurement_event_id,source,source_url,tender_reference,title,buyer,country,publication_date,closing_date,equipment_category,product_family,estimated_value,currency,matched_iati_identifier,match_confidence,match_status
,World Bank,https://example.test,A-1,Kenya lab analyzer procurement,WHO,Kenya,2026-09-01,2026-10-01,Laboratory Equipment,Analyzers,100000,USD,,0,UNMATCHED
"""
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "input.csv").write_text(csv_text, encoding="utf-8")
            db = data_dir / "test.db"
            count = sync_events(data_dir, db, "input.csv")
            output = (data_dir / "procurement_events.csv").read_text(encoding="utf-8")
        self.assertEqual(count, 1)
        self.assertIn("Kenya lab analyzer procurement", output)
