import tempfile
import unittest
from pathlib import Path

from procurement_intelligence.faram_product_specifications import (
    load_specifications,
    specifications_by_product,
    validate_specifications,
)


class FaramProductSpecificationTests(unittest.TestCase):
    def test_empty_registry_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "specifications.csv"
            path.write_text(
                "faram_product_id,specification_name,specification_value,specification_unit,source,source_reference,verification_status,notes\n",
                encoding="utf-8",
            )
            rows = load_specifications(path)
        self.assertEqual(rows, [])
        self.assertEqual(validate_specifications(rows), [])

    def test_missing_provenance_and_unsupported_status_are_detected(self):
        rows = [
            {
                "faram_product_id": "F1",
                "specification_name": "throughput",
                "specification_value": "100",
                "specification_unit": "tests/hour",
                "source": "",
                "source_reference": "",
                "verification_status": "GUESS",
            }
        ]
        issues = validate_specifications(rows)
        self.assertTrue(any(i.field == "source" for i in issues))
        self.assertTrue(any(i.field == "source_reference" for i in issues))
        self.assertTrue(any(i.field == "verification_status" and "unsupported" in i.message for i in issues))

    def test_duplicate_product_specification_is_detected(self):
        base = {
            "faram_product_id": "F1",
            "specification_name": "throughput",
            "specification_value": "100",
            "specification_unit": "tests/hour",
            "source": "datasheet",
            "source_reference": "DS-1",
            "verification_status": "VERIFIED",
        }
        issues = validate_specifications([base, dict(base)])
        self.assertTrue(any("duplicate" in i.message for i in issues))

    def test_only_verified_specifications_are_matchable_by_default(self):
        rows = [
            {"faram_product_id": "F1", "specification_name": "throughput", "specification_value": "100", "specification_unit": "tests/hour", "verification_status": "VERIFIED"},
            {"faram_product_id": "F1", "specification_name": "wavelength", "specification_value": "600", "specification_unit": "nm", "verification_status": "UNVERIFIED"},
            {"faram_product_id": "F2", "specification_name": "throughput", "specification_value": "50", "specification_unit": "tests/hour", "verification_status": "EXPIRED"},
        ]
        grouped = specifications_by_product(rows)
        self.assertEqual([r["specification_name"] for r in grouped["F1"]], ["throughput"])
        self.assertNotIn("F2", grouped)
        self.assertEqual(len(specifications_by_product(rows, verified_only=False)["F1"]), 2)


if __name__ == "__main__":
    unittest.main()
