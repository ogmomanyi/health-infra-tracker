import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import zipfile

from procurement_intelligence.document_evidence import (
    collect_document_evidence,
    persist_rows,
)
from procurement_intelligence.detail_enrichment import enrich_notice_details
from procurement_intelligence.evidence import (
    discover_document_links,
    enrich_evidence_identity,
    extract_document_text,
    stable_process_id,
)


class ProcurementEvidenceTests(unittest.TestCase):
    def test_process_identity_does_not_depend_on_mutable_title(self):
        first = {"source": "UNDP", "source_record_id": "UNDP-KEN-1", "title": "Original"}
        amended = {"source": "UNDP", "source_record_id": "UNDP-KEN-1", "title": "Amended"}
        self.assertEqual(stable_process_id(first), stable_process_id(amended))
        self.assertNotEqual(
            enrich_evidence_identity(first)["procurement_release_id"],
            enrich_evidence_identity(amended)["procurement_release_id"],
        )

    def test_document_discovery_resolves_official_relative_links(self):
        html = '<a href="files/spec.pdf">Technical specification</a><a href="/about">About</a><a href="/search.cfm">Search notices</a>'
        self.assertEqual(
            discover_document_links(html, "https://example.test/notices/1"),
            ["https://example.test/notices/files/spec.pdf"],
        )

    def test_undp_listing_navigation_is_not_document_evidence(self):
        html = '<a href="/index.cfm?cur_lang=en">Procurement Notices</a><a href="/search.cfm">Search Notices</a>'
        self.assertEqual(
            discover_document_links(html, "https://procurement-notices.undp.org/view_negotiation.cfm?nego_id=1"),
            [],
        )

    def test_html_and_docx_text_are_extracted(self):
        text, status = extract_document_text(
            b"<html><body><main>Hematology analyzer model X1</main></body></html>",
            content_type="text/html",
        )
        self.assertEqual(status, "EXTRACTED")
        self.assertIn("Hematology analyzer", text)

        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr(
                "word/document.xml",
                '<w:document xmlns:w="urn:test"><w:body><w:p><w:r><w:t>Model IN75</w:t></w:r></w:p></w:body></w:document>',
            )
        text, status = extract_document_text(
            payload.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertEqual((text, status), ("Model IN75", "EXTRACTED"))

    def test_document_collection_is_bounded_and_persisted(self):
        response = Mock()
        response.content = b"PCR system technical requirements"
        response.headers = {"Content-Type": "text/plain"}
        response.raise_for_status.return_value = None
        session = Mock(); session.get.return_value = response
        events = [{
            "procurement_process_id": "P1",
            "procurement_release_id": "R1",
            "procurement_event_id": "E1",
            "source": "UNDP",
            "document_urls": '["https://example.test/spec.txt", "https://example.test/second.txt"]',
        }]
        rows = collect_document_evidence(
            events, session=session, max_documents=1, fetched_at="2026-09-12T00:00:00+00:00"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["extraction_status"], "EXTRACTED")
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "test.db"
            self.assertEqual(persist_rows(database, rows), 1)

    def test_document_collection_discards_known_listing_page_evidence(self):
        rows = collect_document_evidence([], existing_rows=[{
            "procurement_release_id": "R1",
            "document_url": "https://procurement-notices.undp.org/search.cfm",
            "document_text": "Unrelated global listing text",
        }])
        self.assertEqual(rows, [])

    def test_detail_enrichment_preserves_text_links_and_language(self):
        response = Mock()
        response.text = '<html lang="en"><body><main>PCR system model X1</main><a href="spec.pdf">Specification</a></body></html>'
        response.raise_for_status.return_value = None
        session = Mock(); session.get.return_value = response
        rows = enrich_notice_details(
            [{"source_url": "https://example.test/notices/1", "title": "PCR equipment"}],
            session=session,
            max_records=1,
        )
        self.assertEqual(rows[0]["detail_fetch_status"], "EXTRACTED")
        self.assertEqual(rows[0]["language"], "en")
        self.assertIn("PCR system model X1", rows[0]["notice_text"])
        self.assertIn("https://example.test/notices/spec.pdf", rows[0]["document_urls"])
