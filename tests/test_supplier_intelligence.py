import unittest

from procurement_intelligence.schema import ProcurementEvent
from procurement_intelligence.supplier_intelligence import build_supplier_history


class SupplierIntelligenceTests(unittest.TestCase):
    def test_resolved_variants_share_one_canonical_supplier(self):
        events = [
            ProcurementEvent("1", "World Bank", "", "A", "Lab", "Buyer A", "Kenya", "2026-01-01", "", "Laboratory Equipment", "RFB", supplier_name="EGIS KENYA", supplier_country="Kenya", award_value=100, award_currency="USD", supplier_evidence_status="EXPLICIT", supplier_entity_id="SUP-001", supplier_canonical_name="EGIS Kenya Limited", supplier_match_status="ALIAS_EXACT", supplier_match_confidence=1.0),
            ProcurementEvent("2", "World Bank", "", "B", "Diagnostics", "Buyer B", "Kenya", "2026-02-01", "", "Diagnostics", "RFB", supplier_name="EGIS Kenya Limited", supplier_country="Kenya", award_value=200, award_currency="USD", supplier_evidence_status="EXPLICIT", supplier_entity_id="SUP-001", supplier_canonical_name="EGIS Kenya Limited", supplier_match_status="CANONICAL_EXACT", supplier_match_confidence=1.0),
        ]
        rows = build_supplier_history(events)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["supplier_entity_id"], "SUP-001")
        self.assertEqual(rows[0]["supplier"], "EGIS Kenya Limited")
        self.assertEqual(rows[0]["award_count"], "2")
        self.assertEqual(rows[0]["competitive_position"], "REPEAT_SUPPLIER")
        self.assertEqual(rows[0]["award_value_total"], "300.00")

    def test_repeat_supplier_is_ranked(self):
        events = [
            ProcurementEvent("1", "World Bank", "", "A", "Lab", "Buyer A", "Kenya", "2026-01-01", "", "Laboratory Equipment", "RFB", supplier_name="Acme", supplier_country="Kenya", award_value=100, award_currency="USD", supplier_evidence_status="EXPLICIT", opportunity_status="AWARD_HISTORY", faram_relevance_score=80, procurement_priority="HIGH"),
            ProcurementEvent("2", "World Bank", "", "B", "Diagnostics", "Buyer B", "Kenya", "2026-02-01", "", "Diagnostics", "RFB", supplier_name="Acme", supplier_country="Kenya", award_value=200, award_currency="USD", supplier_evidence_status="EXPLICIT", opportunity_status="AWARD_HISTORY", faram_relevance_score=70, procurement_priority="HIGH"),
        ]
        rows = build_supplier_history(events)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["award_count"], "2")
        self.assertEqual(rows[0]["competitive_position"], "REPEAT_SUPPLIER")
        self.assertEqual(rows[0]["award_value_total"], "300.00")
        self.assertEqual(rows[0]["award_currencies"], "USD")
        self.assertIn("Buyer A", rows[0]["buyers"])
        self.assertIn("Diagnostics", rows[0]["categories"])

    def test_mixed_currency_is_not_summed(self):
        events = [
            ProcurementEvent("1", "World Bank", "", "A", "Lab", "Buyer", "Kenya", "2026-01-01", "", "Laboratory Equipment", "RFB", supplier_name="Acme", supplier_country="Kenya", award_value=100, award_currency="USD", supplier_evidence_status="EXPLICIT"),
            ProcurementEvent("2", "World Bank", "", "B", "Lab", "Buyer", "Kenya", "2026-02-01", "", "Laboratory Equipment", "RFB", supplier_name="Acme", supplier_country="Kenya", award_value=1000, award_currency="KES", supplier_evidence_status="EXPLICIT"),
        ]
        rows = build_supplier_history(events)
        self.assertEqual(rows[0]["award_value_total"], "")
        self.assertEqual(rows[0]["award_currencies"], "KES; USD")


if __name__ == "__main__":
    unittest.main()
