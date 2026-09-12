import unittest

from procurement_intelligence.product_matching import (
    match_catalogue_products,
    match_events,
    match_manufacturers,
    match_product_families,
    match_product_family,
)


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

    def test_ambiguous_brand_words_do_not_create_manufacturer_matches(self):
        manufacturer_rows = [
            {"manufacturer_name": "Traceable", "manufacturer_aliases": "Traceable"},
            {"manufacturer_name": "Becton Dickinson", "manufacturer_aliases": "BD"},
        ]
        self.assertEqual(
            match_manufacturers(
                "Provide traceable results for a basin diagnostic study",
                manufacturer_rows,
            ),
            [],
        )

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

    def test_notice_can_emit_multiple_product_line_items(self):
        rows = match_events([{
            "procurement_event_id": "E6",
            "title": "Supply of hematology analyzers, centrifuges and microscopes",
        }])
        self.assertEqual(
            {row["product_family"] for row in rows},
            {"Hematology Analyzer", "Centrifuge", "Microscope"},
        )
        self.assertEqual(len({row["procurement_line_item_id"] for row in rows}), 3)

    def test_notice_and_document_text_are_searchable_evidence(self):
        rows = match_events([{
            "procurement_event_id": "E7",
            "title": "Hospital equipment lot",
            "notice_text": "Technical schedule: multiparameter patient monitor",
            "document_text": "Portable ultrasound system",
        }])
        self.assertEqual(
            {row["product_family"] for row in rows},
            {"Patient Monitor", "Ultrasound System"},
        )

    def test_unique_catalogue_model_resolves_product_and_manufacturer(self):
        catalogue = [{
            "faram_product_id": "F-1",
            "product_name": "Memmert IN75 laboratory incubator",
            "manufacturer_name": "Memmert",
            "product_family": "Laboratory Incubator",
            "equipment_category": "Laboratory Systems",
            "model": "IN75",
        }]
        matches = match_catalogue_products("Required model IN75", catalogue)
        self.assertEqual(matches[0]["method"], "MODEL_REGISTRY")
        rows = match_events(
            [{"procurement_event_id": "E8", "title": "Required model IN75"}],
            catalogue_rows=catalogue,
        )
        self.assertEqual(rows[0]["manufacturer_names"], "Memmert")
        self.assertEqual(rows[0]["model_evidence"], "IN75")
        self.assertEqual(rows[0]["manufacturer_match_method"], "MODEL_REGISTRY")

    def test_product_family_list_keeps_strongest_evidence_per_family(self):
        matches = match_product_families("PCR molecular diagnostics and PCR systems")
        self.assertEqual(matches[0][0], "Molecular / PCR System")


if __name__ == "__main__":
    unittest.main()
