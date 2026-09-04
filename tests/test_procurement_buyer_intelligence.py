import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from procurement_intelligence.commercial import build_buyer_history
from procurement_intelligence.schema import ProcurementEvent


class ProcurementBuyerIntelligenceTests(unittest.TestCase):
    def _database(self, directory):
        path = Path(directory) / "intelligence.db"
        with sqlite3.connect(path) as conn:
            conn.executescript("""
                CREATE TABLE organisation_entities (
                    entity_id TEXT PRIMARY KEY,
                    canonical_name TEXT NOT NULL UNIQUE,
                    organisation_type TEXT,
                    entity_status TEXT DEFAULT 'ACTIVE'
                );
                CREATE TABLE organisation_aliases (
                    alias_id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    organisation_key TEXT NOT NULL,
                    org_ref TEXT,
                    alias_name TEXT NOT NULL,
                    source_system TEXT NOT NULL DEFAULT 'IATI',
                    is_primary_alias INTEGER DEFAULT 0,
                    match_method TEXT NOT NULL,
                    confidence_score REAL
                );
                CREATE TABLE organisation_relationships (
                    child_entity_id TEXT,
                    parent_entity_id TEXT,
                    relationship_type TEXT
                );
                CREATE TABLE activities (
                    iati_identifier TEXT,
                    project_title TEXT
                );
                INSERT INTO organisation_entities VALUES ('ORG-KEMSA','Kenya Medical Supplies Authority','GOVERNMENT','ACTIVE');
                INSERT INTO organisation_aliases VALUES ('ALIAS-1','ORG-KEMSA','kemsa',NULL,'KEMSA','IATI',1,'MANUAL',1.0);
                INSERT INTO activities VALUES ('P179698','Health Systems Strengthening Project');
            """)
        return path

    def test_canonical_and_unambiguous_alias_merge(self):
        events = [
            ProcurementEvent("p1", "World Bank", "", "RFB-1", "Laboratory analyzers", "Kenya Medical Supplies Authority", "Kenya", "2026-08-01", "2026-10-01", "Laboratory Equipment", "Request for Bids", opportunity_status="ACTIVE_OPPORTUNITY", procurement_priority="HIGH", currency="USD", estimated_value=100000),
            ProcurementEvent("p2", "World Bank", "", "AWD-1", "Laboratory equipment", "KEMSA", "Kenya", "2026-07-01", "", "Laboratory Equipment", "Request for Bids", opportunity_status="AWARD_HISTORY", procurement_priority="LOW", matched_iati_identifier="P179698", match_status="CONFIRMED", currency="USD", estimated_value=200000),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            rows = build_buyer_history(events, database=self._database(tmp), today=date(2026, 9, 3))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["entity_id"], "ORG-KEMSA")
        self.assertEqual(row["buyer"], "Kenya Medical Supplies Authority")
        self.assertEqual(row["buyer_match_status"], "CANONICAL_EXACT")
        self.assertEqual(row["raw_buyer_names"], "KEMSA; Kenya Medical Supplies Authority")
        self.assertEqual(row["event_count"], "2")
        self.assertEqual(row["estimated_value_currency"], "USD")
        self.assertEqual(row["estimated_value_total"], "300000.00")
        self.assertEqual(row["linked_projects"], "Health Systems Strengthening Project")

    def test_mixed_currency_values_do_not_get_summed(self):
        events = [
            ProcurementEvent("p1", "World Bank", "", "A", "Laboratory equipment", "Buyer", "Kenya", "2026-08-01", "", "Laboratory Equipment", "", currency="USD", estimated_value=100000),
            ProcurementEvent("p2", "World Bank", "", "B", "Laboratory equipment", "Buyer", "Kenya", "2026-08-02", "", "Laboratory Equipment", "", currency="EUR", estimated_value=90000),
        ]
        rows = build_buyer_history(events, today=date(2026, 9, 3))
        self.assertEqual(rows[0]["estimated_value_currency"], "MIXED")
        self.assertEqual(rows[0]["estimated_value_total"], "100000.00")


if __name__ == "__main__":
    unittest.main()
