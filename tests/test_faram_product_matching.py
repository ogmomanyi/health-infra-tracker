import unittest

from procurement_intelligence.faram_product_matching import match_events


class FaramProductMatchingTests(unittest.TestCase):
    def setUp(self):
        self.procurement = [{
            "procurement_event_id": "E1",
            "source": "World Bank",
            "tender_reference": "WB-1",
            "title": "Supply of 5-part differential hematology analyzers",
            "buyer": "Ministry of Health",
            "country": "Kenya",
            "publication_date": "2026-09-01",
            "closing_date": "2026-10-01",
            "product_family": "Hematology Analyzer",
            "procurement_category": "Laboratory Equipment",
        }]

    def test_active_exact_family_and_keyword_is_faram_match(self):
        catalogue = [{
            "faram_product_id": "F-001",
            "product_name": "Hematology Analyzer X",
            "manufacturer_name": "Example Principal",
            "product_family": "Hematology Analyzer",
            "equipment_category": "Laboratory Equipment",
            "keywords": "5-part differential;hematology analyzer",
            "exclusion_keywords": "",
            "principal_status": "ACTIVE",
            "territory": "KE;UG;RW",
        }]
        rows = match_events(self.procurement, catalogue)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["match_status"], "FARAM_MATCH")
        self.assertEqual(rows[0]["territory_fit"], "YES")
        self.assertIn("5-part differential", rows[0]["keyword_evidence"])

    def test_exclusion_keyword_blocks_match(self):
        catalogue = [{
            "faram_product_id": "F-002",
            "product_name": "Analyzer Y",
            "manufacturer_name": "Example Principal",
            "product_family": "Hematology Analyzer",
            "equipment_category": "Laboratory Equipment",
            "keywords": "hematology analyzer",
            "exclusion_keywords": "5-part differential",
            "principal_status": "ACTIVE",
            "territory": "KE",
        }]
        rows = match_events(self.procurement, catalogue)
        self.assertEqual(rows[0]["match_status"], "BLOCKED_BY_EXCLUSION")
        self.assertEqual(rows[0]["match_confidence"], 0.0)

    def test_inactive_principal_is_not_actionable(self):
        catalogue = [{
            "faram_product_id": "F-003",
            "product_name": "Analyzer Z",
            "manufacturer_name": "Example Principal",
            "product_family": "Hematology Analyzer",
            "equipment_category": "Laboratory Equipment",
            "keywords": "5-part differential",
            "exclusion_keywords": "",
            "principal_status": "INACTIVE",
            "territory": "KE",
        }]
        rows = match_events(self.procurement, catalogue)
        self.assertEqual(rows[0]["match_status"], "NOT_ACTIONABLE_INACTIVE_PRINCIPAL")

    def test_wrong_territory_is_not_actionable(self):
        catalogue = [{
            "faram_product_id": "F-004",
            "product_name": "Analyzer A",
            "manufacturer_name": "Example Principal",
            "product_family": "Hematology Analyzer",
            "equipment_category": "Laboratory Equipment",
            "keywords": "5-part differential",
            "exclusion_keywords": "",
            "principal_status": "ACTIVE",
            "territory": "UG",
        }]
        rows = match_events(self.procurement, catalogue)
        self.assertEqual(rows[0]["territory_fit"], "NO")
        self.assertEqual(rows[0]["match_status"], "NOT_ACTIONABLE_WRONG_TERRITORY")

    def test_multiple_candidates_are_preserved(self):
        base = {
            "product_family": "Hematology Analyzer",
            "equipment_category": "Laboratory Equipment",
            "keywords": "5-part differential",
            "exclusion_keywords": "",
            "principal_status": "ACTIVE",
            "territory": "KE",
        }
        catalogue = [
            {**base, "faram_product_id": "F-005", "product_name": "Analyzer A", "manufacturer_name": "Principal A"},
            {**base, "faram_product_id": "F-006", "product_name": "Analyzer B", "manufacturer_name": "Principal B"},
        ]
        rows = match_events(self.procurement, catalogue)
        self.assertEqual([row["faram_product_id"] for row in rows], ["F-005", "F-006"])

    def test_empty_catalogue_is_safe(self):
        self.assertEqual(match_events(self.procurement, []), [])

    def test_missing_country_requires_territory_review(self):
        procurement = [dict(self.procurement[0], country="")]
        catalogue = [{
            "faram_product_id": "F-007",
            "product_name": "Analyzer B",
            "manufacturer_name": "Principal B",
            "product_family": "Hematology Analyzer",
            "equipment_category": "Laboratory Equipment",
            "keywords": "5-part differential",
            "exclusion_keywords": "",
            "principal_status": "ACTIVE",
            "territory": "KE",
        }]
        rows = match_events(procurement, catalogue)
        self.assertEqual(rows[0]["territory_fit"], "UNKNOWN")
        self.assertEqual(rows[0]["match_status"], "REQUIRES_TERRITORY_REVIEW")


if __name__ == "__main__":
    unittest.main()
