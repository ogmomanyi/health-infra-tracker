import tempfile
import unittest
from pathlib import Path

from procurement_intelligence.faram_catalogue import load_catalogue, manufacturer_coverage, validate_catalogue


class FaramCatalogueTests(unittest.TestCase):
    def test_empty_catalogue_is_valid_but_contains_no_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalogue.csv"
            path.write_text(
                "faram_product_id,product_name,manufacturer_name,product_family,equipment_category,model,keywords,exclusion_keywords,principal_status,territory,source,notes\n",
                encoding="utf-8",
            )
            rows = load_catalogue(path)
        self.assertEqual(rows, [])
        self.assertEqual(manufacturer_coverage(rows), {})
        self.assertEqual(validate_catalogue(rows), [])

    def test_required_fields_and_duplicates_are_detected(self):
        rows = [
            {"faram_product_id": "F1", "product_name": "Analyzer", "manufacturer_name": "Principal", "product_family": "Hematology Analyzer", "equipment_category": "Laboratory Equipment", "principal_status": "ACTIVE", "territory": "KE"},
            {"faram_product_id": "F1", "product_name": "Analyzer", "manufacturer_name": "Principal", "product_family": "Hematology Analyzer", "equipment_category": "Laboratory Equipment", "principal_status": "ACTIVE", "territory": "KE"},
            {"faram_product_id": "F2", "product_name": "", "manufacturer_name": "Principal", "product_family": "Hematology Analyzer", "equipment_category": "Laboratory Equipment", "principal_status": "ACTIVE", "territory": "KE"},
        ]
        issues = validate_catalogue(rows)
        self.assertTrue(any(i.field == "faram_product_id" for i in issues))
        self.assertTrue(any(i.field == "product_name" and "blank" in i.message for i in issues))

    def test_manufacturer_coverage_counts_active_products(self):
        rows = [
            {"faram_product_id": "F1", "product_name": "Analyzer", "manufacturer_name": "Principal A", "principal_status": "ACTIVE", "territory": "KE"},
            {"faram_product_id": "F2", "product_name": "Analyzer 2", "manufacturer_name": "Principal A", "principal_status": "INACTIVE", "territory": "KE"},
            {"faram_product_id": "F3", "product_name": "Analyzer 3", "manufacturer_name": "Principal B", "principal_status": "PROSPECT", "territory": "UG"},
        ]
        coverage = manufacturer_coverage(rows)
        self.assertEqual(coverage["principal a"]["product_count"], 2)
        self.assertEqual(coverage["principal a"]["active_product_count"], 1)
        self.assertEqual(coverage["principal b"]["active_product_count"], 0)


if __name__ == "__main__":
    unittest.main()
