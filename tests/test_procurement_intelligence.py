import tempfile
import unittest
from pathlib import Path

from procurement_intelligence.ingest import read_events, stable_event_id, write_events
from procurement_intelligence.matcher import match_event
from procurement_intelligence.schema import ProcurementEvent


class ProcurementIntelligenceTests(unittest.TestCase):
    def test_event_id_is_stable(self):
        self.assertEqual(
            stable_event_id("UNGM", "A-1", "Lab equipment"),
            stable_event_id("UNGM", "A-1", "Lab equipment"),
        )

    def test_round_trip_csv(self):
        event = ProcurementEvent(
            "proc_1", "UNGM", "https://example.test", "A-1", "Lab equipment",
            "WHO", "Kenya", "2026-09-01", "2026-10-01", "Laboratory Equipment",
            "Analyzers",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.csv"
            write_events(path, [event])
            loaded = list(read_events(path))
        self.assertEqual(loaded[0].title, event.title)

    def test_matching_is_evidence_only(self):
        event = ProcurementEvent(
            "proc_1", "UNGM", "", "A-1",
            "Kenya laboratory equipment strengthening", "WHO", "Kenya", "", "",
            "Laboratory Equipment", "Analyzers",
        )
        projects = [{
            "iati_identifier": "P-1",
            "project_title": "Kenya laboratory equipment strengthening",
            "funding_agencies": "WHO",
            "country_names": "Kenya",
        }]
        result = match_event(event, projects)
        self.assertEqual(result["matched_iati_identifier"], "P-1")
        self.assertIn(result["match_status"], {"POSSIBLE", "CONFIRMED"})

    def test_explicit_iati_identifier_is_confirmed(self):
        event = ProcurementEvent(
            "proc_2", "UNGM", "", "A-2", "Unrelated title", "Unknown", "Uganda",
            "", "", "Laboratory Equipment", "Analyzers", matched_iati_identifier="P-2",
        )
        projects = [{"iati_identifier": "P-2", "project_title": "Different project"}]
        result = match_event(event, projects)
        self.assertEqual(result["matched_iati_identifier"], "P-2")
        self.assertEqual(result["match_status"], "CONFIRMED")
        self.assertEqual(result["match_confidence"], 100.0)

    def test_country_and_equipment_alone_do_not_match(self):
        event = ProcurementEvent(
            "proc_3", "UNGM", "", "A-3", "Supply notice", "", "Kenya", "", "",
            "Laboratory Equipment", "Analyzers",
        )
        projects = [{
            "iati_identifier": "P-3",
            "project_title": "Maternal health policy reform",
            "funding_agencies": "UNICEF",
            "country_names": "Kenya",
            "equipment_target_summary": "Laboratory Equipment",
        }]
        result = match_event(event, projects)
        self.assertEqual(result["match_status"], "UNMATCHED")
        self.assertEqual(result["matched_iati_identifier"], "")

    def test_weak_text_does_not_force_a_match(self):
        event = ProcurementEvent(
            "proc_4", "UNGM", "", "A-4", "General supplies", "", "Kenya", "", "",
            "Medical Devices", "",
        )
        projects = [{
            "iati_identifier": "P-4",
            "project_title": "Community health systems",
            "funding_agencies": "WHO",
            "country_names": "Kenya",
        }]
        result = match_event(event, projects)
        self.assertEqual(result["match_status"], "UNMATCHED")
        self.assertEqual(result["matched_iati_identifier"], "")


if __name__ == "__main__":
    unittest.main()
