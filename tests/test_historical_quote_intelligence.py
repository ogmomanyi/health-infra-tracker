import unittest

from procurement_intelligence.historical_quote_intelligence import build_summary, familiarity_match


class HistoricalQuoteIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {
                "evidence_id": "HQE-001",
                "product_name": "SpectraMax i3x",
                "manufacturer_name": "Molecular Devices",
                "product_family": "Multimode Microplate Reader",
                "model": "i3x",
                "evidence_type": "tender_fit_and_pricing",
                "supplier_email": "viktoria@moldev.com",
            },
            {
                "evidence_id": "HQE-002",
                "product_name": "SpectraMax i3x",
                "manufacturer_name": "Molecular Devices",
                "product_family": "Multimode Microplate Reader",
                "model": "i3x",
                "evidence_type": "quotation",
                "supplier_email": "sales@moldev.com",
            },
            {
                "evidence_id": "HQE-003",
                "product_name": "HemoScreen Analyzer",
                "manufacturer_name": "PixCell",
                "product_family": "Hematology Analyzer",
                "model": "HemoScreen Analyzer",
                "evidence_type": "market_evaluation_and_pricing",
                "supplier_email": "sales@pixcell.com",
            },
            {
                "evidence_id": "HQE-005",
                "product_name": "Centrifuge main PCB",
                "manufacturer_name": "Unknown",
                "product_family": "Centrifuge",
                "model": "20150350",
                "evidence_type": "procurement_request",
                "supplier_email": "state@example.gov",
            },
        ]

    def test_exact_product_scores_above_family_only(self):
        exact = familiarity_match(
            "Procurement of SpectraMax i3x",
            "",
            "Multimode Microplate Reader",
            "Molecular Devices",
            self.rows,
        )
        family = familiarity_match(
            "Procurement of multimode microplate readers",
            "",
            "Multimode Microplate Reader",
            "",
            self.rows,
        )
        self.assertGreater(exact["historical_familiarity_score"], family["historical_familiarity_score"])
        self.assertEqual(exact["historical_familiarity_band"], "EXACT")

    def test_repeated_evidence_increases_familiarity(self):
        summary = build_summary(self.rows)
        i3x = next(row for row in summary if row["model"] == "i3x")
        self.assertEqual(i3x["historical_quote_count"], "2")
        self.assertEqual(i3x["supplier_count"], "2")
        self.assertEqual(i3x["evidence_strength"], "HIGH")

    def test_historical_evidence_does_not_create_current_catalogue_match(self):
        result = familiarity_match(
            "SpectraMax i3x procurement",
            "",
            "Multimode Microplate Reader",
            "Molecular Devices",
            self.rows,
        )
        self.assertEqual(result["historical_familiarity_status"], "HISTORICAL_COMMERCIAL_EVIDENCE")
        self.assertNotIn("FARAM_MATCH", result.values())

    def test_external_procurement_only_row_is_excluded(self):
        summary = build_summary(self.rows)
        self.assertFalse(any(row["model"] == "20150350" for row in summary))

    def test_missing_manufacturer_is_safe(self):
        result = familiarity_match(
            "HemoScreen Analyzer",
            "",
            "Hematology Analyzer",
            "",
            self.rows,
        )
        self.assertGreater(result["historical_familiarity_score"], 0)


if __name__ == "__main__":
    unittest.main()
