import csv
import tempfile
import unittest
from pathlib import Path

from procurement_intelligence.account_commercial_memory import build_memory, write_memory


class AccountCommercialMemoryTests(unittest.TestCase):
    def test_family_familiarity_is_traceable_and_catalogue_status_is_separate(self):
        accounts = [{
            "target_account_id": "acct_1",
            "account_name": "Test Hospital",
            "organisation_entity_id": "org_1",
            "top_needs": "Hematology Analyzer; Ultrasound System",
        }]
        evidence = [{
            "evidence_id": "HQE-025",
            "product_name": "Hemoglobin Pro Analyzer",
            "manufacturer_name": "YiCare Medical",
            "product_family": "Hematology Analyzer",
            "model": "Hemoglobin Pro",
            "supplier_email": "admin@yicaremedical.com",
            "evidence_type": "quotation",
        }]
        catalogue = [{
            "manufacturer_name": "YiCare Medical",
            "product_family": "Hematology Analyzer",
            "principal_status": "active",
        }]

        rows = build_memory(accounts, evidence, catalogue)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["commercial_memory_evidence_ids"], "HQE-025")
        self.assertEqual(rows[0]["commercial_memory_manufacturers"], "YiCare Medical")
        self.assertEqual(rows[0]["commercial_memory_product_families"], "Hematology Analyzer")
        self.assertEqual(rows[0]["catalogue_matched_families"], "Hematology Analyzer")
        self.assertGreater(float(rows[0]["commercial_memory_score"]), 0)

    def test_empty_accounts_write_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, fields in [
                ("accounts.csv", ["target_account_id", "account_name", "organisation_entity_id", "top_needs"]),
                ("evidence.csv", ["evidence_id", "product_name", "manufacturer_name", "product_family", "model", "supplier_email", "evidence_type"]),
                ("catalogue.csv", ["manufacturer_name", "product_family", "principal_status"]),
            ]:
                with (root / name).open("w", newline="", encoding="utf-8") as handle:
                    csv.DictWriter(handle, fieldnames=fields).writeheader()
            output = root / "output.csv"
            self.assertEqual(write_memory(root / "accounts.csv", root / "evidence.csv", root / "catalogue.csv", output), 0)
            with output.open(encoding="utf-8") as handle:
                self.assertEqual(next(csv.reader(handle)), [
                    "target_account_id", "account_name", "organisation_entity_id",
                    "commercial_memory_score", "commercial_memory_band",
                    "commercial_memory_evidence_count", "commercial_memory_evidence_ids",
                    "commercial_memory_manufacturers", "commercial_memory_product_families",
                    "catalogue_matched_families", "recommended_action",
                ])


if __name__ == "__main__":
    unittest.main()
