#!/usr/bin/env python3

import unittest
from datetime import date

from intelligence_enrichment import (
    amount_to_usd,
    canonical_donor_name,
    extract_equipment_signals,
    extract_manufacturers,
    split_values,
    tender_model,
)


class IntelligenceEnrichmentTests(unittest.TestCase):
    def test_donor_families_collapse_aliases(self):
        self.assertEqual(canonical_donor_name("GAVI The Vaccine Alliance"), "Gavi, the Vaccine Alliance")
        self.assertEqual(canonical_donor_name("Gavi, the Vaccine Alliance"), "Gavi, the Vaccine Alliance")
        self.assertEqual(
            canonical_donor_name("The Global Fund to Fight AIDS, Tuberculosis and Malaria"),
            "The Global Fund",
        )
        self.assertEqual(canonical_donor_name("USA USAID"), "USAID")
        self.assertEqual(canonical_donor_name("USAID/Food for Peace"), "USAID")
        self.assertEqual(canonical_donor_name("WHO Foundation"), "WHO Foundation")
        self.assertEqual(
            canonical_donor_name("WHO - World Health Organization"),
            "World Health Organization",
        )

    def test_usd_conversion_and_unknown_currency(self):
        amount, status = amount_to_usd(100, "EUR")
        self.assertEqual(status, "CONVERTED")
        self.assertGreater(amount, 100)
        _, mixed_status = amount_to_usd(100, "MIXED")
        self.assertEqual(mixed_status, "UNKNOWN_CURRENCY")

    def test_html_entities_do_not_split_organisation_names(self):
        self.assertEqual(
            split_values("Bill &amp; Melinda Gates Foundation; World Health Organization"),
            ["Bill & Melinda Gates Foundation", "World Health Organization"],
        )

    def test_equipment_distinguishes_direct_from_inferred(self):
        direct = extract_equipment_signals(
            "Procurement of GeneXpert diagnostic analysers",
            sector_codes="12250",
        )
        self.assertEqual(direct["equipment_evidence"], "direct_keyword")
        self.assertIn("Diagnostic Equipment", direct["equipment_target_summary"])

        inferred = extract_equipment_signals(
            "Primary health care policy support",
            sector_codes="12230",
        )
        self.assertEqual(inferred["equipment_evidence"], "sector_inferred")
        self.assertEqual(inferred["equipment_target_summary"], "Facility Infrastructure")

    def test_tender_model_does_not_treat_monitor_as_a_window(self):
        result = tender_model(
            {
                "equipment_evidence": "direct_keyword",
                "direct_equipment_categories": "Diagnostic Equipment",
                "procurement_signal": "Yes",
                "activity_status_code": "2",
                "future_disbursement_usd": 250000,
                "next_disbursement_date": "2026-10-01",
                "predicted_tender_window": "Q4 2026",
                "prediction_basis": "next planned disbursement",
                "implementing_partners": "Ministry of Health",
                "last_updated": "2026-07-01",
            },
            date(2026, 8, 20),
        )
        self.assertEqual(result["tender_stage"], "Likely procurement")
        self.assertEqual(result["tender_window"], "Q4 2026")
        self.assertGreaterEqual(result["tender_probability"], 70)

        watch = tender_model(
            {
                "equipment_evidence": "none",
                "predicted_tender_window": "Monitor",
                "activity_status_code": "2",
            },
            date(2026, 8, 20),
        )
        self.assertEqual(watch["tender_window"], "")
        self.assertEqual(watch["tender_stage"], "Watch")

    def test_manufacturer_requires_explicit_mention(self):
        self.assertEqual(
            extract_manufacturers("Installation of Cepheid GeneXpert systems"),
            "Cepheid",
        )
        self.assertEqual(extract_manufacturers("Laboratory strengthening programme"), "")


if __name__ == "__main__":
    unittest.main()
