import csv
import tempfile
import unittest
from pathlib import Path

from procurement_intelligence.manufacturer_extraction import extract_explicit_manufacturer_brand
from procurement_intelligence.manufacturer_intelligence import build_manufacturer_history
from procurement_intelligence.schema import ProcurementEvent
from procurement_intelligence.sources.world_bank import normalize_notices


class ManufacturerIntelligenceTests(unittest.TestCase):
    def test_explicit_manufacturer_and_brand_labels(self):
        manufacturer, brand, status = extract_explicit_manufacturer_brand(
            notice_text="Manufacturer: Sysmex Corporation; Brand: Sysmex; Model: XN-1000"
        )
        self.assertEqual((manufacturer, brand, status), ("Sysmex Corporation", "Sysmex", "EXPLICIT"))

    def test_structured_fields_are_supported(self):
        result = extract_explicit_manufacturer_brand(
            {"manufacturer": "Abbott Laboratories", "brand": "Alinity"}
        )
        self.assertEqual(result, ("Abbott Laboratories", "Alinity", "EXPLICIT"))

    def test_supplier_name_is_never_used_as_manufacturer(self):
        result = extract_explicit_manufacturer_brand(
            {"supplier_name": "Acme Diagnostics Ltd"},
            "Awarded Bidder: Acme Diagnostics Ltd",
        )
        self.assertEqual(result, ("", "", "NONE"))

    def test_conflicting_manufacturer_labels_are_ambiguous(self):
        result = extract_explicit_manufacturer_brand(
            notice_text="Manufacturer: Sysmex Corporation; Manufacturer: Mindray"
        )
        self.assertEqual(result, ("", "", "AMBIGUOUS"))

    def test_world_bank_normalization_carries_manufacturer_evidence(self):
        records = normalize_notices([{
            "id": "AWD-MFG-1",
            "bid_description": "Supply of hematology analyzers",
            "notice_type": "Contract Award",
            "awarded_bidder_name": "Acme Diagnostics Ltd",
            "notice_text": "Awarded Bidder: Acme Diagnostics Ltd; Manufacturer: Sysmex Corporation; Brand: Sysmex",
        }])
        self.assertEqual(records[0]["supplier_name"], "Acme Diagnostics Ltd")
        self.assertEqual(records[0]["manufacturer_name"], "Sysmex Corporation")
        self.assertEqual(records[0]["brand_name"], "Sysmex")
        self.assertEqual(records[0]["manufacturer_evidence_status"], "EXPLICIT")

    def test_empty_catalogue_reports_unknown_coverage(self):
        event = ProcurementEvent(
            "1", "World Bank", "https://example.test/award", "A", "Hematology analyzers",
            "Buyer", "Kenya", "2026-08-01", "", "Laboratory Equipment", "Request for Bids",
            supplier_name="Acme", supplier_country="Kenya", supplier_evidence_status="EXPLICIT",
            manufacturer_name="Sysmex Corporation", brand_name="Sysmex",
            manufacturer_evidence_status="EXPLICIT",
        )
        with tempfile.TemporaryDirectory() as tmp:
            catalogue = Path(tmp) / "catalogue.csv"
            catalogue.write_text("faram_product_id,product_name,manufacturer_name,product_family,equipment_category,model,keywords,exclusion_keywords,principal_status,territory,source,notes\n", encoding="utf-8")
            rows = build_manufacturer_history([event], catalogue)
        self.assertEqual(rows[0]["faram_catalogue_status"], "CATALOGUE_NOT_POPULATED")
        self.assertEqual(rows[0]["competitive_gap"], "UNKNOWN_COVERAGE")

    def test_catalogue_match_and_principal_gap_are_distinguished(self):
        events = [
            ProcurementEvent("1", "World Bank", "u", "A", "Lab", "Buyer", "Kenya", "2026-01-01", "", "Laboratory Equipment", "RFB", supplier_name="A", manufacturer_name="Sysmex Corporation", manufacturer_evidence_status="EXPLICIT"),
            ProcurementEvent("2", "World Bank", "u", "B", "Lab", "Buyer", "Kenya", "2026-02-01", "", "Laboratory Equipment", "RFB", supplier_name="B", manufacturer_name="Mindray", manufacturer_evidence_status="EXPLICIT"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            catalogue = Path(tmp) / "catalogue.csv"
            with catalogue.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["faram_product_id", "product_name", "manufacturer_name"])
                writer.writeheader(); writer.writerow({"faram_product_id": "F-1", "product_name": "Hematology Analyzer", "manufacturer_name": "Sysmex Corporation"})
            rows = build_manufacturer_history(events, catalogue)
        by_mfg = {row["manufacturer_name"]: row for row in rows}
        self.assertEqual(by_mfg["Sysmex Corporation"]["faram_catalogue_status"], "FARAM_CATALOGUE_MATCH")
        self.assertEqual(by_mfg["Mindray"]["competitive_gap"], "PRINCIPAL_ACQUISITION_CANDIDATE")


if __name__ == "__main__":
    unittest.main()
