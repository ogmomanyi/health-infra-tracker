import unittest
from datetime import date

from procurement_intelligence.commercial_opportunity_workspace import build_opportunity_workspace


class CommercialOpportunityWorkspaceTests(unittest.TestCase):
    def action(self, event_ids="e1; e2", category="QUALIFY_AND_BID"):
        return {
            "action_id": "ACTION-e1",
            "target_account_id": "acct-1",
            "account_name": "Buyer One",
            "country": "Kenya",
            "account_type": "Government",
            "crm_stage": "Open",
            "commercial_account_priority_score": "78.5",
            "commercial_account_priority_tier": "ACT_NOW",
            "action_category": category,
            "action_status": "OPEN",
            "assigned_owner": "",
            "action_due_date": "2026-09-20",
            "next_closing_date": "2026-09-20",
            "estimated_opportunity_value": "1000000.00",
            "catalogue_fit_status": "FARAM_MATCH",
            "catalogue_matched_products": "FARAM-1",
            "priority_reason": "strong buyer demand",
            "recommended_action": "Engage buyer immediately.",
            "procurement_event_ids": event_ids,
            "familiarity_evidence_ids": "HQE-001",
        }

    def event(self, event_id="e1", reference="T-001"):
        return {
            "procurement_event_id": event_id,
            "source": "World Bank",
            "source_url": "https://example.test/tender",
            "tender_reference": reference,
            "title": "Laboratory equipment",
            "buyer": "Buyer One",
            "country": "Kenya",
            "publication_date": "2026-09-01",
            "closing_date": "2026-09-20",
            "equipment_category": "Laboratory Equipment",
            "product_family": "Analyzer",
            "estimated_value": "500000",
            "currency": "USD",
            "procurement_stage": "TENDER",
        }

    def test_fans_out_one_action_to_event_level_opportunities(self):
        rows = build_opportunity_workspace(
            [self.action()], [self.event("e1"), self.event("e2", "T-002")], today=date(2026, 9, 4)
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["opportunity_id"] for row in rows}, {"OPP-e1", "OPP-e2"})
        self.assertEqual(rows[0]["commercial_account_priority_score"], "78.5")

    def test_event_fields_are_joined(self):
        rows = build_opportunity_workspace([self.action("e1")], [self.event()], today=date(2026, 9, 4))
        self.assertEqual(rows[0]["tender_reference"], "T-001")
        self.assertEqual(rows[0]["source"], "World Bank")
        self.assertEqual(rows[0]["days_to_closing"], "16")
        self.assertEqual(rows[0]["next_activity"], "Qualify tender and confirm bid/no-bid")

    def test_account_action_is_retained_when_event_snapshot_is_missing(self):
        rows = build_opportunity_workspace([self.action("missing")], [], today=date(2026, 9, 4))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["opportunity_id"], "OPP-ACTION-e1")
        self.assertEqual(rows[0]["procurement_event_id"], "")
        self.assertEqual(rows[0]["next_activity"], "Qualify tender and confirm bid/no-bid")

    def test_account_development_action_without_events_remains_account_work(self):
        rows = build_opportunity_workspace(
            [self.action("", category="PIPELINE_DEVELOPMENT")], [], today=date(2026, 9, 4)
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["opportunity_id"], "OPP-ACTION-e1")
        self.assertIn("Develop account pipeline", rows[0]["next_activity"])

    def test_duplicate_event_ids_do_not_duplicate_work(self):
        rows = build_opportunity_workspace(
            [self.action("e1; e1")], [self.event("e1")], today=date(2026, 9, 4)
        )
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
