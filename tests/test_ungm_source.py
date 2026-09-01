import unittest

from procurement_intelligence.sources.ungm import normalize_notice, normalize_notices


class UNGMSourceTests(unittest.TestCase):
    def test_normalizes_common_notice_fields(self):
        event = normalize_notice({
            "reference": "UNGM-001",
            "notice_title": "Supply of laboratory analyzers",
            "organization": "WHO",
            "country_name": "Kenya",
            "published": "2026-09-01",
            "deadline": "2026-10-01",
            "category": "Laboratory Equipment",
            "product": "Analyzers",
            "value": "125000",
            "currency_code": "USD",
            "url": "https://example.test/ungm-001",
        })
        self.assertEqual(event.source, "UNGM")
        self.assertEqual(event.tender_reference, "UNGM-001")
        self.assertEqual(event.buyer, "WHO")
        self.assertEqual(event.country, "Kenya")
        self.assertEqual(event.estimated_value, 125000.0)
        self.assertEqual(event.currency, "USD")
        self.assertTrue(event.procurement_event_id.startswith("proc_"))

    def test_deduplicates_notices(self):
        record = {"reference": "UNGM-001", "title": "Supply of analyzers"}
        events = normalize_notices([record, dict(record)])
        self.assertEqual(len(events), 1)


if __name__ == "__main__":
    unittest.main()
