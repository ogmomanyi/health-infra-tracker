import unittest
from datetime import date

from procurement_intelligence.commercial_action_queue import build_action_queue


class CommercialActionQueueTests(unittest.TestCase):
    def row(self, tier="ACT_NOW", fit="FARAM_MATCH", active="1", closing="2026-09-20"):
        return {
            "target_account_id": "acct-1",
            "account_name": "Buyer One",
            "country": "Kenya",
            "account_type": "Government",
            "crm_stage": "Open",
            "commercial_account_priority_score": "78.5",
            "commercial_account_priority_tier": tier,
            "recommended_action": "Engage buyer immediately.",
            "next_closing_date": closing,
            "active_opportunities": active,
            "high_priority_opportunities": "1",
            "upcoming_pipeline": "0",
            "estimated_opportunity_value": "1000000.00",
            "catalogue_fit_status": fit,
            "catalogue_matched_events": "1",
            "catalogue_matched_products": "FARAM-1",
            "procurement_event_ids": "e1",
            "familiarity_evidence_ids": "HQE-001",
            "priority_reason": "strong buyer demand; 1 active opportunity; current Faram catalogue fit",
        }

    def test_actionable_priority_becomes_bid_action(self):
        rows = build_action_queue([self.row()], today=date(2026, 9, 4))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["action_id"], "ACTION-e1")
        self.assertEqual(rows[0]["action_category"], "QUALIFY_AND_BID")
        self.assertEqual(rows[0]["action_status"], "OPEN")
        self.assertEqual(rows[0]["days_to_closing"], "16")
        self.assertEqual(rows[0]["action_due_date"], "2026-09-20")

    def test_missing_fit_creates_resolution_action(self):
        rows = build_action_queue([self.row(fit="NO_VERIFIED_CATALOGUE_MATCH")], today=date(2026, 9, 4))
        self.assertEqual(rows[0]["action_category"], "RESOLVE_PRODUCT_OR_TERRITORY_FIT")

    def test_monitor_accounts_are_not_work_queue_actions(self):
        rows = build_action_queue([self.row(tier="MONITOR")], today=date(2026, 9, 4))
        self.assertEqual(rows, [])

    def test_action_queue_preserves_traceability(self):
        row = self.row()
        row["procurement_event_ids"] = "e1; e2"
        rows = build_action_queue([row], today=date(2026, 9, 4))
        self.assertEqual(rows[0]["procurement_event_ids"], "e1; e2")
        self.assertEqual(rows[0]["familiarity_evidence_ids"], "HQE-001")


if __name__ == "__main__":
    unittest.main()
