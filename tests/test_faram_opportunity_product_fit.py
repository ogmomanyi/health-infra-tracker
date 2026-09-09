import unittest

from procurement_intelligence.faram_opportunity_product_fit import build_fit


class FaramOpportunityProductFitTests(unittest.TestCase):
    def candidate(self, **overrides):
        row = {
            "procurement_event_id": "evt-1",
            "tender_reference": "T-1",
            "title": "Biochemistry analyzer | throughput: 100 tests/hour",
            "buyer": "Buyer",
            "country": "Kenya",
            "faram_product_id": "F-001",
            "product_name": "Analyzer A",
            "manufacturer_name": "Principal A",
            "match_status": "FARAM_MATCH",
            "match_confidence": "95",
        }
        row.update(overrides)
        return row

    def test_verified_evidence_produces_pass(self):
        rows = build_fit(
            [self.candidate()],
            [{
                "faram_product_id": "F-001", "specification_name": "throughput",
                "specification_value": "120", "specification_unit": "tests/hour",
                "source": "datasheet", "source_reference": "DS-1", "verification_status": "VERIFIED",
            }],
        )
        self.assertEqual(rows[0]["technical_status"], "PASS")
        self.assertEqual(rows[0]["technical_passed"], "1")
        self.assertEqual(rows[0]["match_confidence"], "95")

    def test_missing_evidence_is_unknown(self):
        rows = build_fit([self.candidate()], [])
        self.assertEqual(rows[0]["technical_status"], "UNKNOWN")
        self.assertEqual(rows[0]["technical_unknown"], "1")

    def test_unverified_evidence_does_not_pass(self):
        rows = build_fit(
            [self.candidate()],
            [{
                "faram_product_id": "F-001", "specification_name": "throughput",
                "specification_value": "120", "specification_unit": "tests/hour",
                "source": "datasheet", "source_reference": "DS-1", "verification_status": "UNVERIFIED",
            }],
        )
        self.assertEqual(rows[0]["technical_status"], "UNKNOWN")

    def test_explicit_failure_is_preserved(self):
        rows = build_fit(
            [self.candidate()],
            [{
                "faram_product_id": "F-001", "specification_name": "throughput",
                "specification_value": "80", "specification_unit": "tests/hour",
                "source": "datasheet", "source_reference": "DS-1", "verification_status": "VERIFIED",
            }],
        )
        self.assertEqual(rows[0]["technical_status"], "FAIL")
        self.assertEqual(rows[0]["technical_failed"], "1")


if __name__ == "__main__":
    unittest.main()
