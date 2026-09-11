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

    def test_canonical_manufacturer_rows_expand_explicit_matching(self):
        matches = match_manufacturers(
            "Tender requires a Molecular Devices reader",
            [{
                "manufacturer_name": "Molecular Devices",
                "manufacturer_aliases": "Molecular Devices; MD Instruments",
            }],
        )
        self.assertEqual(matches, [("Molecular Devices", "Molecular Devices")])

    def test_catalogue_product_family_requires_specific_language(self):
        self.assertEqual(
            match_product_family("Supply of a class II biological safety cabinet")[:2],
            ("Biological Safety Cabinet", "Laboratory Systems"),
        )
        self.assertEqual(match_product_family("Women energy incubator programme"), ("", "", ""))

    def test_canonical_entity_ids_are_resolved(self):
        rows = match_events(
            [{"procurement_event_id": "E4", "title": "Apheresis machine"}],
            equipment_rows=[{"equipment_category": "Blood Bank Equipment", "equipment_entity_id": "equip-blood"}],
            manufacturer_rows=[],
        )
        self.assertEqual(rows[0]["equipment_entity_id"], "equip-blood")

    def test_canonical_manufacturer_aliases_resolve_to_entity_ids(self):
        rows = match_events(
            [{"procurement_event_id": "E5", "title": "Supply from Thermo Scientific"}],
            manufacturer_rows=[{
                "manufacturer_entity_id": "mfr-thermo",
                "manufacturer_name": "Thermo Fisher",
                "manufacturer_aliases": "Thermo Fisher; Thermo Scientific",
            }],
        )
        self.assertEqual(rows[0]["manufacturer_names"], "Thermo Fisher")
        self.assertEqual(rows[0]["manufacturer_entity_ids"], "mfr-thermo")


if __name__ == "__main__":
    unittest.main()
