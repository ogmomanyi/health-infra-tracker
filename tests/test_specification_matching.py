import unittest

from procurement_intelligence.specification_matching import (
    Specification,
    compare_specifications,
    extract_specifications,
)


class SpecificationMatchingTests(unittest.TestCase):
    def test_extracts_labelled_numeric_specs(self):
        specs = extract_specifications("Throughput: 100 tests/hour; Sample volume: 10 uL; Wavelength: 600 nm")
        self.assertEqual([(s.name, s.value, s.unit) for s in specs], [
            ("throughput", 100.0, "tests/hour"),
            ("sample volume", 0.01, "ml"),
            ("wavelength", 600.0, "nm"),
        ])

    def test_extracts_text_specs(self):
        specs = extract_specifications("Differential: 5-part; Connectivity: LIS")
        self.assertEqual(specs[0].value, "5-part")
        self.assertEqual(specs[1].value, "lis")

    def test_throughput_is_a_minimum(self):
        result = compare_specifications(
            [Specification("throughput", 100.0, "tests/hour")],
            [Specification("throughput", 120.0, "tests/hour")],
        )
        self.assertEqual(result["overall_status"], "PASS")
        self.assertEqual(result["score"], 100.0)

    def test_missing_evidence_requires_review(self):
        result = compare_specifications(
            [Specification("throughput", 100.0, "tests/hour")],
            [],
        )
        self.assertEqual(result["overall_status"], "REVIEW")
        self.assertEqual(result["unknown"], 1)

    def test_explicit_failure_is_not_hidden(self):
        result = compare_specifications(
            [Specification("throughput", 100.0, "tests/hour")],
            [Specification("throughput", 80.0, "tests/hour")],
        )
        self.assertEqual(result["overall_status"], "FAIL")
        self.assertEqual(result["failed"], 1)

    def test_unit_normalization(self):
        result = compare_specifications(
            [Specification("sample volume", 0.01, "ml")],
            [Specification("sample volume", 10.0, "ul")],
        )
        self.assertEqual(result["overall_status"], "PASS")


if __name__ == "__main__":
    unittest.main()
