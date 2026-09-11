import unittest
from datetime import date

from procurement_intelligence.commercial_bid_intelligence import build_guidance


class CommercialBidIntelligenceTests(unittest.TestCase):
    def base(self):
        return {
            "product_family": "Analyzer",
            "catalogue_fit_status": "FARAM_MATCH",
            "territory_fit": "YES",
            "principal_status": "ACTIVE",
            "closing_date": "2026-09-30",
        }

    def test_pass_proceeds_without_scoring(self):
        result = build_guidance(
            self.base(), [{"technical_status": "PASS"}], [], today=date(2026, 9, 11)
        )
        self.assertEqual(result["commercial_posture"], "PROCEED_TO_COMMERCIAL_REVIEW")
        self.assertEqual(result["technical_status"], "PASS")
        self.assertEqual(result["closing_urgency"], "NORMAL")

    def test_fail_holds_and_does_not_decide_bid(self):
        result = build_guidance(
            self.base(), [{"technical_status": "FAIL"}], [], today=date(2026, 9, 11)
        )
        self.assertEqual(result["commercial_posture"], "HOLD_FOR_TECHNICAL_RESOLUTION")
        self.assertIn("failed specification", " ".join(result["preparation_actions"]).lower())

    def test_unknown_is_evidence_review(self):
        result = build_guidance(
            self.base(), [{"technical_status": "UNKNOWN"}], [], today=date(2026, 9, 11)
        )
        self.assertEqual(result["commercial_posture"], "EVIDENCE_REVIEW_REQUIRED")
        self.assertEqual(result["technical_status"], "UNKNOWN")

    def test_historical_memory_is_context_not_price(self):
        result = build_guidance(
            self.base(),
            [{"technical_status": "PASS"}],
            [{
                "product_family": "Analyzer",
                "representation_signal": "ACTIVE_COMMERCIAL",
                "outcome": "QUOTED",
                "evidence_id": "HQE-1",
            }],
            today=date(2026, 9, 11),
        )
        self.assertEqual(result["historical_memory_count"], 1)
        self.assertIn("current selling price", result["pricing_guidance"])
        self.assertIn("HQE-1", result["historical_evidence_ids"])

    def test_urgent_closing_adds_execution_action(self):
        opportunity = {**self.base(), "closing_date": "2026-09-13"}
        result = build_guidance(
            opportunity, [{"technical_status": "PASS"}], [], today=date(2026, 9, 11)
        )
        self.assertEqual(result["closing_urgency"], "URGENT")
        self.assertTrue(
            any("lead time" in action.lower() for action in result["preparation_actions"])
        )


if __name__ == "__main__":
    unittest.main()
