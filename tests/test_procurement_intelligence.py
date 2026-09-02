import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from procurement_intelligence.ingest import read_events, stable_event_id, write_events
from procurement_intelligence.matcher import match_event
from procurement_intelligence.schema import ProcurementEvent
from procurement_intelligence.sources.afdb import normalize_notice_records, parse_notice_page
from procurement_intelligence.sources.rss import normalize_notices
from procurement_intelligence.sources.undp import parse_notice_page as parse_undp_notice_page
from procurement_intelligence.sources.world_bank import fetch_notices


class ProcurementIntelligenceTests(unittest.TestCase):
    def test_event_id_is_stable(self):
        self.assertEqual(stable_event_id("World Bank", "A-1", "Lab equipment"), stable_event_id("World Bank", "A-1", "Lab equipment"))

    def test_round_trip_csv(self):
        event = ProcurementEvent("proc_1", "World Bank", "https://example.test", "A-1", "Lab equipment", "WHO", "Kenya", "2026-09-01", "2026-10-01", "Laboratory Equipment", "Analyzers")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.csv"
            write_events(path, [event])
            loaded = list(read_events(path))
        self.assertEqual(loaded[0].title, event.title)

    def test_world_bank_fetch_uses_public_json(self):
        response = Mock()
        response.json.return_value = {"procnotices": [{"id": "WB-1", "title": "Laboratory equipment"}]}
        response.raise_for_status.return_value = None
        with patch("procurement_intelligence.sources.world_bank.requests.get", return_value=response) as get:
            records = fetch_notices(country_codes=["KE"])
        self.assertEqual(records[0]["id"], "WB-1")
        self.assertEqual(get.call_args.kwargs["params"]["countrycode_exact"], "KE")

    def test_rss_records_are_normalized(self):
        records = normalize_notices([{"title": "Supply of laboratory equipment", "tender_reference": "AFDB-1", "source_url": "https://example.test/1"}], source="AfDB")
        self.assertEqual(records[0]["source"], "AfDB")
        self.assertEqual(records[0]["tender_reference"], "AFDB-1")

    def test_afdb_records_are_normalized(self):
        records = normalize_notice_records([{"title": "Supply of laboratory equipment", "reference": "AFDB-2", "country": "Kenya", "project_reference": "P-22"}])
        self.assertEqual(records[0]["source"], "AfDB")
        self.assertEqual(records[0]["project_reference"], "P-22")
        self.assertEqual(records[0]["procurement_stage"], "")

    def test_afdb_page_parser_is_conservative(self):
        html = '''<html><body><a href="/notice/1">Supply of laboratory diagnostic equipment</a><a href="/about">About the Bank</a></body></html>'''
        records = parse_notice_page(html, "https://www.afdb.org/notices", country="Kenya")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["country"], "Kenya")
        self.assertEqual(records[0]["source_url"], "https://www.afdb.org/notice/1")

    def test_afdb_multiple_pages_are_supported(self):
        with patch("procurement_intelligence.sources.afdb.fetch_page", side_effect=[
            '<a href="/notice/1">Supply of laboratory diagnostic equipment</a>',
            '<a href="/notice/2">Invitation for bids for laboratory analyzers</a>',
        ]) as fetch_page:
            from unittest.mock import patch as run_patch
            import sys
            from procurement_intelligence import run
            argv = ["run.py", "--source", "afdb", "--page-url", "https://www.afdb.org/notices/1", "--page-url", "https://www.afdb.org/notices/2"]
            with run_patch.object(sys, "argv", argv), run_patch.object(run, "load_projects", return_value=[]), run_patch.object(run, "write_events"), run_patch.object(run, "persist_events"):
                run.main()
            self.assertEqual(fetch_page.call_count, 2)

    def test_undp_public_page_parser(self):
        html = '''
        <div class="notice-card">
          <a href="/notice/123">Supply of laboratory diagnostic equipment</a>
          <span>Reference: UNDP-KEN-123</span>
          <span>Country: Kenya</span>
          <span>Deadline: 30/09/2026</span>
          <span>Posted: 01/09/2026</span>
        </div>
        <a href="/about">About UNDP</a>
        '''
        records = parse_undp_notice_page(html, "https://procurement-notices.undp.org/")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source"], "UNDP")
        self.assertEqual(records[0]["country"], "Kenya")
        self.assertEqual(records[0]["tender_reference"], "UNDP-KEN-123")
        self.assertEqual(records[0]["closing_date"], "30/09/2026")
        self.assertEqual(records[0]["procurement_stage"], "NOTICE")

    def test_matching_is_evidence_only(self):
        event = ProcurementEvent("proc_1", "World Bank", "", "A-1", "Kenya laboratory equipment strengthening", "WHO", "Kenya", "", "", "Laboratory Equipment", "Analyzers")
        projects = [{"iati_identifier": "P-1", "project_title": "Kenya laboratory equipment strengthening", "funding_agencies": "WHO", "country_names": "Kenya"}]
        result = match_event(event, projects)
        self.assertEqual(result["matched_iati_identifier"], "P-1")
        self.assertIn(result["match_status"], {"POSSIBLE", "CONFIRMED"})

    def test_country_and_equipment_alone_do_not_match(self):
        event = ProcurementEvent("proc_3", "World Bank", "", "A-3", "Supply notice", "", "Kenya", "", "", "Laboratory Equipment", "Analyzers")
        projects = [{"iati_identifier": "P-3", "project_title": "Maternal health policy reform", "funding_agencies": "UNICEF", "country_names": "Kenya", "equipment_target_summary": "Laboratory Equipment"}]
        result = match_event(event, projects)
        self.assertEqual(result["match_status"], "UNMATCHED")


if __name__ == "__main__":
    unittest.main()
