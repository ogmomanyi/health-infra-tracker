import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from procurement_intelligence.source_health import build_source_health, sync_manifest


class ProcurementSourceHealthTests(unittest.TestCase):
    def test_required_missing_source_is_failed(self):
        rows = build_source_health([], [], required_sources=["UNDP"])
        self.assertEqual(rows[0]["health_status"], "FAILED")

    def test_current_failed_collection_is_not_masked_by_history(self):
        rows = build_source_health(
            [{"procurement_event_id": "OLD", "source": "UNDP", "source_url": "u"}],
            [],
            required_sources=["UNDP"],
            collection_rows=[{"source": "UNDP", "run_status": "FAILED"}],
        )
        self.assertEqual(rows[0]["health_status"], "FAILED")
        self.assertIn("current source run", rows[0]["health_issues"])

    def test_partial_current_collection_fails_strict_health_contract(self):
        rows = build_source_health(
            [{"procurement_event_id": "E1", "source": "AfDB", "source_url": "u"}],
            [],
            collection_rows=[{"source": "AfDB", "run_status": "PARTIAL"}],
        )
        self.assertEqual(rows[0]["health_status"], "FAILED")
        self.assertIn("partially", rows[0]["health_issues"])

    def test_matches_are_counted_by_unique_event(self):
        events = [{
            "procurement_event_id": "E1", "source": "UNDP", "source_url": "u",
            "tender_reference": "R1", "publication_date": "2026-09-01",
            "closing_date": "2026-10-01", "buyer": "Buyer",
            "opportunity_status": "ACTIVE_OPPORTUNITY",
        }]
        matches = [
            {"procurement_event_id": "E1", "source": "UNDP", "product_family": "Centrifuge"},
            {"procurement_event_id": "E1", "source": "UNDP", "product_family": "Microscope", "manufacturer_names": "Acme"},
        ]
        row = build_source_health(events, matches)[0]
        self.assertEqual(row["product_match_count"], "1")
        self.assertEqual(row["manufacturer_match_count"], "1")
        self.assertEqual(row["health_status"], "HEALTHY")

    def test_manifest_and_market_summary_share_current_pipeline_metadata(self):
        with TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            manifest_path = data_dir / "manifest.json"
            manifest_path.write_text(
                json.dumps({"pipeline_version": "old", "row_counts": {}, "files": {}}),
                encoding="utf-8",
            )
            (data_dir / "market_summary.json").write_text(
                json.dumps({"pipeline_version": "old", "layer_counts": {}}),
                encoding="utf-8",
            )
            sync_manifest(manifest_path, data_dir)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            summary = json.loads(
                (data_dir / "market_summary.json").read_text(encoding="utf-8")
            )
        self.assertEqual(manifest["pipeline_version"], summary["pipeline_version"])
        self.assertEqual(manifest["pipeline_layers"], summary["pipeline_layers"])
        intelligence = next(
            layer for layer in manifest["pipeline_layers"]
            if layer["layer"] == "INTELLIGENCE"
        )
        self.assertIn("procurement_manufacturer_relationships", intelligence["datasets"])
