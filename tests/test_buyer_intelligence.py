import unittest
from datetime import date

from procurement_intelligence.buyer_intelligence import build_buyer_history
from procurement_intelligence.schema import ProcurementEvent


class BuyerIntelligenceTests(unittest.TestCase):
    def test_raw_buyer_grouping_is_deterministic(self):
        events = [
            ProcurementEvent("p1", "AfDB", "", "A-1", "Laboratory analyzer", "Ministry of Health", "Uganda", "2026-08-01", "", "Laboratory Equipment", "", opportunity_status="AWARD_HISTORY", procurement_priority="LOW"),
            ProcurementEvent("p2", "AfDB", "", "A-2", "Laboratory analyzer", "Ministry of Health", "Uganda", "2026-08-02", "", "Laboratory Equipment", "", opportunity_status="AWARD_HISTORY", procurement_priority="LOW"),
        ]
        rows = build_buyer_history(events, database=None, today=date(2026, 9, 3))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_count"], "2")
        self.assertEqual(rows[0]["recurring_categories"], "Laboratory Equipment")
        self.assertGreater(float(rows[0]["buyer_demand_score"]), 0)

    def test_safe_alias_resolution_requires_database(self):
        events = [
            ProcurementEvent("p1", "World Bank", "", "RFB-1", "Supply of laboratory analyzers", "KEMSA", "Kenya", "2026-08-01", "2026-10-01", "Laboratory Equipment", "Request for Bids", procurement_stage="Invitation for Bids", opportunity_status="ACTIVE_OPPORTUNITY", procurement_priority="HIGH", estimated_value=100000),
        ]
        rows = build_buyer_history(events, database=None, today=date(2026, 9, 3))
        self.assertEqual(rows[0]["buyer_match_status"], "UNMATCHED")
        self.assertEqual(rows[0]["entity_id"], "")

    def test_demand_score_is_not_faram_familiarity(self):
        events = [
            ProcurementEvent("p1", "World Bank", "", "RFB-1", "Supply of hematology analyzers", "Buyer", "Kenya", "2026-09-01", "2026-10-01", "Laboratory Equipment", "Request for Bids", opportunity_status="ACTIVE_OPPORTUNITY", procurement_priority="HIGH", estimated_value=1000000),
        ]
        row = build_buyer_history(events, database=None, today=date(2026, 9, 3))[0]
        self.assertIn("buyer_demand_score", row)
        self.assertNotIn("faram_account_score", row)
        self.assertIn("buyer_demand_tier", row)


if __name__ == "__main__":
    unittest.main()
