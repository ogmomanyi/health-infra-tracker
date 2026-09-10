import unittest

from procurement_intelligence.bid_decision_guidance import guidance


class BidDecisionGuidanceTests(unittest.TestCase):
    def test_all_technical_failure_recommends_no_bid_without_setting_decision(self):
        result = guidance({"days_to_closing": "10"}, [{"technical_status": "FAIL", "territory_fit": "YES"}])
        self.assertEqual(result["posture"], "DO_NOT_BID")
        self.assertIn("TECHNICAL_FAILURE", result["reason_codes"])
        self.assertFalse(result["automatic_decision"])

    def test_unknown_evidence_is_review_not_failure(self):
        result = guidance({"days_to_closing": "20"}, [{"technical_status": "UNKNOWN", "territory_fit": "YES"}])
        self.assertEqual(result["posture"], "TECHNICAL_REVIEW")
        self.assertNotIn("TECHNICAL_FAILURE", result["reason_codes"])
        self.assertFalse(result["automatic_decision"])

    def test_pass_can_proceed_to_human_review(self):
        result = guidance({"days_to_closing": "30"}, [{"technical_status": "PASS", "territory_fit": "YES"}])
        self.assertEqual(result["posture"], "PROCEED_TO_BID_REVIEW")
        self.assertFalse(result["automatic_decision"])

    def test_missed_closing_holds_decision(self):
        result = guidance({"days_to_closing": "-1"}, [{"technical_status": "PASS", "territory_fit": "YES"}])
        self.assertEqual(result["posture"], "HOLD")
        self.assertIn("CLOSING_DATE_PASSED", result["reason_codes"])

    def test_canonical_priority_is_not_consumed_or_changed(self):
        opportunity = {
            "commercial_account_priority_score": 88.0,
            "commercial_account_priority_tier": "ACT_NOW",
            "days_to_closing": "5",
        }
        result = guidance(opportunity, [{"technical_status": "PASS", "territory_fit": "YES"}])
        self.assertEqual(opportunity["commercial_account_priority_score"], 88.0)
        self.assertEqual(opportunity["commercial_account_priority_tier"], "ACT_NOW")
        self.assertEqual(result["posture"], "PROCEED_TO_BID_REVIEW")


if __name__ == "__main__":
    unittest.main()
