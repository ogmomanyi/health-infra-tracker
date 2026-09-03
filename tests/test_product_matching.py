import unittest

from procurement_intelligence.product_matching import match_events, match_product_family, match_manufacturers


class ProductMatchingTests(unittest.TestCase):
    def test_explicit_product_family_and_manufacturer_match(self):
        rows = match_events([{
            "procurement_event_id": "E1",
            "source": "World Bank",
            "tender_reference": "WB-1",
            "title": "Supply of hematology analyzers - Sysmex",
            "buyer": "Ministry of Health",
            "country": "Kenya",
            "publication_date": "2026-09-01",
            "closing_date": "2026-10-01",
        }])
        self.assertEqual(rows[0]["product_family"], "Hematology Analyzer")
        self.assertEqual(rows[0]["manufacturer_names"], "Sysmex")
        self.assertEqual(rows[0]["match_status"], "MATCHED_PRODUCT_AND_MANUFACTURER")
        self.assertIn("product family phrase", rows[0]["match_evidence"])

    def test_product_family_does_not_infer_manufacturer(self):
        rows = match_events([{
            "procurement_event_id": "E2",
            "title": "Supply of clinical chemistry analyzers",
            "equipment_category": "Laboratory Equipment",
            "product_family": "",
            "procurement_stage": "Invitation for bids",
        }])
        self.assertEqual(rows[0]["product_family"], "Clinical Chemistry Analyzer")
        self.assertEqual(rows[0]["manufacturer_names"], "")
        self.assertEqual(rows[0]["match_status"], "MATCHED_PRODUCT_FAMILY")

    def test_manufacturer_only_is_not_product_match(self):
        rows = match_events([{
            "procurement_event_id": "E3",
            "title": "Supply of laboratory equipment - Roche",
        }])
        self.assertEqual(rows[0]["manufacturer_names"], "Roche")
        self.assertEqual(rows[0]["product_family"], "")
        self.assertEqual(rows[0]["match_status"], "MANUFACTURER_ONLY")

    def test_generic_category_does_not_create_product_family(self):
        family, category, evidence = match_product_family("Medical equipment for regional hospital")
        self.assertEqual((family, category, evidence), ("", "", ""))

    def test_manufacturer_alias_is_explicit(self):
        self.assertEqual(match_manufacturers("Supply from B. Braun") [0][0], "B. Braun")

    def test_canonical_entity_ids_are_resolved(self):
        rows = match_events(
            [{"procurement_event_id": "E4", "title": "Apheresis machine"}],
            equipment_rows=[{"equipment_category": "Blood Bank Equipment", "equipment_entity_id": "equip-blood"}],
            manufacturer_rows=[],
        )
        self.assertEqual(rows[0]["equipment_entity_id"], "equip-blood")


if __name__ == "__main__":
    unittest.main()
