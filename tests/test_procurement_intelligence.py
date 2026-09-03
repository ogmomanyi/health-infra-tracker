import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from procurement_intelligence.ingest import read_events, stable_event_id, write_events
from procurement_intelligence.matcher import match_event
from procurement_intelligence.run import build_events, classify_opportunity_status, score_faram_relevance
from procurement_intelligence.schema import ProcurementEvent
from procurement_intelligence.sources.afdb import normalize_notice_records, parse_notice_page
from procurement_intelligence.sources.rss import normalize_notices as normalize_rss_notices
from procurement_intelligence.sources.undp import parse_notice_page as parse_undp_notice_page
from procurement_intelligence.sources.world_bank import classify_equipment, fetch_notices, normalize_notices as normalize_world_bank_notices
from procurement_intelligence.commercial import build_buyer_history


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

    def test_world_bank_fetch_uses_country_name_filter(self):
        response = Mock()
        response.json.return_value = {"procnotices": [{"id": "WB-1", "title": "Laboratory equipment"}]}
        response.raise_for_status.return_value = None
        with patch("procurement_intelligence.sources.world_bank.requests.get", return_value=response) as get:
            records = fetch_notices(country_codes=["KE"])
        self.assertEqual(records[0]["id"], "WB-1")
        self.assertEqual(get.call_args.kwargs["params"]["project_ctry_name"], "Kenya")

    def test_world_bank_live_schema_is_normalized(self):
        records = normalize_world_bank_notices([{
            "id": "OP00465854",
            "bid_reference_no": "KE-KEMSA-512246-GO-RFB",
            "bid_description": "Supply and Delivery of Examination Gloves and Surgical Gloves sterile",
            "contact_organization": "Kenya Medical Supplies Authority",
            "project_ctry_name": "Kenya",
            "noticedate": "31-Aug-2026",
            "submission_deadline_date": "2026-10-01T00:00:00Z",
            "procurement_group": "GO",
            "procurement_method_name": "Request for Bids",
            "project_id": "P179698",
            "notice_type": "Invitation for Bids",
        }])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["tender_reference"], "KE-KEMSA-512246-GO-RFB")
        self.assertEqual(records[0]["buyer"], "Kenya Medical Supplies Authority")
        self.assertEqual(records[0]["country"], "Kenya")
        self.assertEqual(records[0]["publication_date"], "2026-08-31")
        self.assertEqual(records[0]["closing_date"], "2026-10-01")
        self.assertEqual(records[0]["equipment_category"], "PPE")
        self.assertEqual(records[0]["product_family"], "Request for Bids")
        self.assertEqual(records[0]["project_reference"], "P179698")
        self.assertEqual(records[0]["procurement_stage"], "Invitation for Bids")

    def test_world_bank_equipment_categories(self):
        self.assertEqual(classify_equipment("Supply of hematology analyzer"), "Laboratory Equipment")
        self.assertEqual(classify_equipment("Procurement of PCR diagnostic test kits"), "Diagnostics")
        self.assertEqual(classify_equipment("Supply of blood bank refrigerators"), "Blood Banking")
        self.assertEqual(classify_equipment("Supply of surgical gloves"), "PPE")
        self.assertEqual(classify_equipment("Supply of office furniture", procurement_group="GO"), "GO")

    def test_rss_records_are_normalized(self):
        records = normalize_rss_notices([{"title": "Supply of laboratory equipment", "tender_reference": "AFDB-1", "source_url": "https://example.test/1"}], source="AfDB")
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

    def test_undp_public_table_parser_matches_live_field_names(self):
        html = '''
        <table>
          <tr><th>Title</th><th>Ref No</th><th>UNDP Office/Country</th><th>Procurement Process</th><th>Deadline</th><th>Posted</th></tr>
          <tr>
            <td><a href="/notice/123">Supply of laboratory diagnostic equipment</a></td>
            <td>UNDP-KEN-123</td>
            <td>UNDP-KEN/KENYA</td>
            <td>RFQ - Request for quotation</td>
            <td>30-Sep-26</td>
            <td>01-Sep-26</td>
          </tr>
        </table>
        '''
        records = parse_undp_notice_page(html, "https://procurement-notices.undp.org/")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source"], "UNDP")
        self.assertEqual(records[0]["country"], "KENYA")
        self.assertEqual(records[0]["tender_reference"], "UNDP-KEN-123")
        self.assertEqual(records[0]["closing_date"], "2026-09-30")
        self.assertEqual(records[0]["publication_date"], "2026-09-01")
        self.assertEqual(records[0]["procurement_stage"], "NOTICE")

    def test_undp_card_parser_remains_supported(self):
        html = '''
        <div class="notice-card">
          <a href="/notice/123">Supply of laboratory diagnostic equipment</a>
          <span>Reference: UNDP-KEN-123</span>
          <span>Country: Kenya</span>
          <span>Deadline: 30/09/2026</span>
          <span>Posted: 01/09/2026</span>
        </div>
        '''
        records = parse_undp_notice_page(html, "https://procurement-notices.undp.org/")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["country"], "Kenya")
        self.assertEqual(records[0]["tender_reference"], "UNDP-KEN-123")
        self.assertEqual(records[0]["closing_date"], "2026-09-30")
        self.assertEqual(records[0]["publication_date"], "2026-09-01")

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

    def test_active_opportunity_classification(self):
        event = ProcurementEvent("p", "World Bank", "", "RFB-1", "Supply of hematology analyzers", "Buyer", "Kenya", "2026-09-01", "2026-10-01", "Laboratory Equipment", "Request for Bids", procurement_stage="Invitation for Bids")
        self.assertEqual(classify_opportunity_status(event, date(2026, 9, 2)), "ACTIVE_OPPORTUNITY")
        score, priority, reason = score_faram_relevance(event)
        self.assertGreaterEqual(score, 70)
        self.assertEqual(priority, "HIGH")
        self.assertIn("active bid", reason.lower())

    def test_award_is_history_not_active(self):
        event = ProcurementEvent("p", "World Bank", "", "AWD-1", "Supply of laboratory equipment", "", "Kenya", "2026-08-01", "", "Laboratory Equipment", "Request for Bids", procurement_stage="Contract Award")
        self.assertEqual(classify_opportunity_status(event, date(2026, 9, 2)), "AWARD_HISTORY")
        score, _, _ = score_faram_relevance(event)
        self.assertLess(score, 70)

    def test_procurement_plan_and_closed_opportunity(self):
        plan = ProcurementEvent("p", "World Bank", "", "PLAN-1", "Laboratory equipment procurement plan", "", "Uganda", "2026-09-01", "", "Laboratory Equipment", "", procurement_stage="Procurement Plan")
        closed = ProcurementEvent("c", "World Bank", "", "RFB-2", "Supply of diagnostic equipment", "", "Rwanda", "2026-08-01", "2026-08-31", "Diagnostics", "Request for Bids", procurement_stage="Invitation for Bids")
        self.assertEqual(classify_opportunity_status(plan, date(2026, 9, 2)), "PROCUREMENT_PLAN")
        self.assertEqual(classify_opportunity_status(closed, date(2026, 9, 2)), "CLOSED_OPPORTUNITY")

    def test_build_events_populates_enrichment_fields(self):
        notice = {
            "procurement_event_id": "p",
            "source": "World Bank",
            "source_url": "",
            "tender_reference": "RFB-1",
            "title": "Supply of PCR diagnostic equipment",
            "buyer": "Buyer",
            "country": "Kenya",
            "publication_date": "2026-09-01",
            "closing_date": "2026-10-01",
            "equipment_category": "Diagnostics",
            "product_family": "Request for Bids",
            "estimated_value": "",
            "currency": "",
            "matched_iati_identifier": "",
            "match_confidence": 0.0,
            "match_status": "UNMATCHED",
            "project_reference": "P-1",
            "procurement_stage": "Invitation for Bids",
            "procurement_priority": "",
            "opportunity_status": "",
            "faram_relevance_score": 0.0,
            "faram_relevance_reason": "",
        }
        event = build_events([notice], [])[0]
        self.assertEqual(event.opportunity_status, "ACTIVE_OPPORTUNITY")
        self.assertGreater(event.faram_relevance_score, 0)
        self.assertTrue(event.faram_relevance_reason)
        self.assertEqual(event.procurement_priority, "HIGH")

    def test_buyer_history_normalizes_safe_alias_and_scores_account(self):
        events = [
            ProcurementEvent("p1", "World Bank", "", "RFB-1", "Supply of laboratory analyzers", "Kenya Medical Supplies Authority", "Kenya", "2026-08-01", "2026-10-01", "Laboratory Equipment", "Request for Bids", procurement_stage="Invitation for Bids", opportunity_status="ACTIVE_OPPORTUNITY", procurement_priority="HIGH", estimated_value=100000),
            ProcurementEvent("p2", "World Bank", "", "AWD-1", "Supply of laboratory equipment", "KEMSA", "Kenya", "2026-07-01", "", "Laboratory Equipment", "Request for Bids", procurement_stage="Contract Award", opportunity_status="AWARD_HISTORY", procurement_priority="LOW", matched_iati_identifier="P-179698", match_status="CONFIRMED", estimated_value=200000),
        ]
        class FakeConn:
            pass
        rows = build_buyer_history(events, database=None, today=date(2026, 9, 3))
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["buyer"] for row in rows}, {"Kenya Medical Supplies Authority", "KEMSA"})

    def test_buyer_history_raw_grouping_is_deterministic(self):
        events = [
            ProcurementEvent("p1", "AfDB", "", "A-1", "Laboratory analyzer", "Ministry of Health", "Uganda", "2026-08-01", "", "Laboratory Equipment", "", opportunity_status="AWARD_HISTORY", procurement_priority="LOW"),
            ProcurementEvent("p2", "AfDB", "", "A-2", "Laboratory analyzer", "Ministry of Health", "Uganda", "2026-08-02", "", "Laboratory Equipment", "", opportunity_status="AWARD_HISTORY", procurement_priority="LOW"),
        ]
        rows = build_buyer_history(events, database=None, today=date(2026, 9, 3))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_count"], "2")
        self.assertEqual(rows[0]["recurring_categories"], "Laboratory Equipment")
        self.assertGreater(float(rows[0]["faram_account_score"]), 0)


if __name__ == "__main__":
    unittest.main()
