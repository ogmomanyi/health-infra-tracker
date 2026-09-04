import unittest
from datetime import date

from procurement_intelligence.commercial_account_priority import build_priority


class CommercialAccountPriorityTests(unittest.TestCase):
    def account(self):
        return {
            "target_account_id": "acct-1",
            "organisation_entity_id": "org-1",
            "account_name": "Buyer One",
            "account_type": "Government",
            "country_codes": "KE; UG",
            "country_names": "Kenya; Uganda",
            "crm_stage": "Open",
        }

    def buyer(self, score="80", tier="A"):
        return {
            "entity_id": "org-1",
            "canonical_buyer": "Buyer One",
            "buyer_demand_score": score,
            "buyer_demand_tier": tier,
            "active_opportunities": "1",
        }

    def event(self, event_id="e1", country="Kenya"):
        return {
            "procurement_event_id": event_id,
            "buyer": "Buyer One",
            "canonical_buyer": "Buyer One",
            "entity_id": "org-1",
            "country": country,
            "opportunity_status": "ACTIVE_OPPORTUNITY",
            "procurement_priority": "HIGH",
            "estimated_value": "1000000",
            "closing_date": "2026-09-20",
            "tender_reference": event_id,
            "title": "Laboratory equipment",
        }

    def match(self, event_id="e1"):
        return {
            "procurement_event_id": event_id,
            "buyer": "Buyer One",
            "country": "KE",
            "faram_product_id": "FARAM-1",
            "match_status": "FARAM_MATCH",
        }

    def memory(self):
        return {
            "target_account_id": "acct-1",
            "commercial_memory_score": "6",
            "commercial_memory_band": "HIGH",
            "commercial_memory_evidence_count": "2",
            "commercial_memory_evidence_ids": "HQE-001; HQE-002",
        }

    def test_current_fit_and_demand_produce_actionable_priority(self):
        rows = build_priority(
            [self.account()], [self.buyer()], [self.event()], [self.match()], [self.memory()],
            today=date(2026, 9, 4),
        )
        row = rows[0]
        self.assertEqual(row["catalogue_fit_status"], "FARAM_MATCH")
        self.assertEqual(row["commercial_account_priority_tier"], "ACT_NOW")
        self.assertGreaterEqual(float(row["commercial_account_priority_score"]), 70)
        self.assertIn("current Faram catalogue fit", row["priority_reason"])
        self.assertEqual(row["procurement_event_ids"], "e1")

    def test_duplicate_event_does_not_inflate_opportunity_or_timing(self):
        duplicate = dict(self.event())
        rows = build_priority(
            [self.account()], [self.buyer()], [self.event(), duplicate], [self.match(), self.match()], [self.memory()],
            today=date(2026, 9, 4),
        )
        row = rows[0]
        self.assertEqual(row["active_opportunities"], "1")
        self.assertEqual(row["catalogue_matched_events"], "1")
        self.assertEqual(row["procurement_event_ids"], "e1")

    def test_missing_catalogue_match_is_not_labelled_as_incapable(self):
        rows = build_priority(
            [self.account()], [self.buyer(score="50", tier="B")], [self.event()], [], [self.memory()],
            today=date(2026, 9, 4),
        )
        self.assertEqual(rows[0]["catalogue_fit_status"], "NO_VERIFIED_CATALOGUE_MATCH")
        self.assertEqual(float(rows[0]["catalogue_fit_score"]), 0.0)

    def test_country_code_and_country_name_interoperate(self):
        rows = build_priority(
            [self.account()], [self.buyer()], [self.event(country="KE")], [self.match()], [self.memory()],
            today=date(2026, 9, 4),
        )
        self.assertEqual(rows[0]["active_opportunities"], "1")


if __name__ == "__main__":
    unittest.main()
