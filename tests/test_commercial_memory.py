import unittest

from procurement_intelligence.commercial_memory import build_summary, normalize_evidence


class CommercialMemoryTests(unittest.TestCase):
    def test_normalize_evidence_derives_supplier_signal_and_outcome(self):
        rows = [{
            "evidence_id": "HQE-023", "product_name": "Thermo Fisher scientific equipment and consumables",
            "manufacturer_name": "Thermo Fisher Scientific", "product_family": "Life Science / Laboratory Equipment",
            "model": "", "category": "Laboratory Equipment", "evidence_type": "order_and_business_review",
            "supplier_email": "orders.em@thermofisher.com", "source_email_id": "email-1",
            "notes": "Historical PO/order correspondence plus business review evidence",
        }]
        result = normalize_evidence(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["memory_id"], "FCM-HQE-023")
        self.assertEqual(result[0]["supplier_company"], "Thermo Fisher Scientific")
        self.assertEqual(result[0]["outcome"], "ORDERED")
        self.assertEqual(result[0]["evidence_strength"], "HIGH")
        self.assertEqual(result[0]["representation_signal"], "TRANSACTIONAL")

    def test_inquiry_outcomes_are_distinct_from_quotes(self):
        rows = normalize_evidence([
            {"evidence_id": "HQE-I1", "evidence_type": "quotation_inquiry"},
            {"evidence_id": "HQE-I2", "evidence_type": "request_for_pricing"},
            {"evidence_id": "HQE-Q1", "evidence_type": "quotation"},
        ])
        self.assertEqual(rows[0]["outcome"], "INQUIRY")
        self.assertEqual(rows[1]["outcome"], "INQUIRY")
        self.assertEqual(rows[2]["outcome"], "QUOTED")

    def test_enrichment_overrides_missing_event_fields_without_mutating_source_row(self):
        source = {"evidence_id": "HQE-016", "evidence_type": "tender_fit_and_pricing", "supplier_email": "viktoria.rumjantseva@moldev.com"}
        enriched = normalize_evidence([source], {"HQE-016": {
            "evidence_id": "HQE-016", "event_date": "2026-07-03", "country": "KE",
            "customer_or_project": "Kenya laboratory tender", "outcome_override": "TENDER_SUPPORT",
            "representation_signal_override": "ACTIVE_COMMERCIAL", "notes_override": "Verified from Outlook evidence",
        }})
        self.assertEqual(enriched[0]["memory_id"], "FCM-HQE-016")
        self.assertEqual(enriched[0]["event_date"], "2026-07-03")
        self.assertEqual(enriched[0]["country"], "KE")
        self.assertEqual(enriched[0]["customer_or_project"], "Kenya laboratory tender")
        self.assertEqual(enriched[0]["outcome"], "TENDER_SUPPORT")
        self.assertEqual(enriched[0]["notes"], "Verified from Outlook evidence")
        self.assertNotIn("event_date", source)

    def test_external_and_competitive_evidence_do_not_enter_summary(self):
        rows = normalize_evidence([
            {"evidence_id": "HQE-005", "product_name": "Centrifuge main PCB", "manufacturer_name": "Unknown",
             "product_family": "Centrifuge", "model": "20150350", "evidence_type": "procurement_request",
             "supplier_email": "KiharaRM@state.gov", "notes": "External procurement request; not evidence of current Faram representation"},
            {"evidence_id": "HQE-019", "product_name": "Cytation multimode reader", "manufacturer_name": "Agilent / BioTek",
             "product_family": "Cytation Multimode Reader", "model": "Cytation", "evidence_type": "tender_reference_only",
             "supplier_email": "viktoria.rumjantseva@moldev.com", "notes": "Competitive/reference evidence, not Faram representation"},
        ])
        self.assertEqual(build_summary(rows), [])

    def test_summary_joins_current_catalogue_status(self):
        memory = normalize_evidence([{
            "evidence_id": "HQE-016", "product_name": "SpectraMax i3x", "manufacturer_name": "Molecular Devices",
            "product_family": "Multimode Microplate Reader", "model": "i3x", "evidence_type": "tender_fit_and_pricing",
            "supplier_email": "viktoria.rumjantseva@moldev.com", "notes": "Explicit tender comparison",
        }])
        catalogue = [{"manufacturer_name": "Molecular Devices", "product_family": "Multimode Microplate Reader", "principal_status": "active"}]
        summary = build_summary(memory, catalogue)
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["current_catalogue_status"], "CATALOGUE_MATCH")
        self.assertEqual(summary[0]["commercial_familiarity_score"], "2")


if __name__ == "__main__":
    unittest.main()
