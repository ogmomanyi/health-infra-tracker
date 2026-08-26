#!/usr/bin/env python3

import csv
import json
import sqlite3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def csv_header(path: Path) -> set[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        return set(next(reader))


def csv_count(path: Path) -> int:
    with path.open(newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle))


class DashboardContractTests(unittest.TestCase):
    def test_dashboard_references_generated_commercial_datasets(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertNotIn("```", html)

        for path in [
            "data/target_accounts.csv",
            "data/recommended_actions.csv",
            "data/programme_intelligence.csv",
            "data/opportunities.csv",
            "data/engagements.csv",
            "data/crm_notes.csv",
            "data/donor_intelligence.csv",
            "data/equipment_intelligence.csv",
            "data/tender_predictions.csv",
            "data/market_summary.json",
        ]:
            self.assertIn(path, html)

        self.assertIn("openProgrammeDetail", html)
        self.assertIn("detailOverlay", html)
        self.assertIn("data-programme-id", html)

    def test_manifest_declares_layered_pipeline(self):
        manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["pipeline_version"], "3.2-project-detail-intelligence")
        self.assertEqual(
            [layer["layer"] for layer in manifest["pipeline_layers"]],
            [
                "RAW",
                "NORMALIZED",
                "CANONICAL",
                "INTELLIGENCE",
                "COMMERCIAL",
                "PREDICTIVE_PRODUCT",
            ],
        )

        for name in [
            "activities",
            "organisation_entities",
            "opportunity_scores",
            "programme_intelligence",
            "donor_intelligence",
            "target_accounts",
            "recommended_actions",
            "equipment_intelligence",
            "tender_predictions",
        ]:
            self.assertIn(name, manifest["files"])
            self.assertGreater(manifest["row_counts"][name], 0)

    def test_enriched_csv_schemas_are_available(self):
        expected_headers = {
            "donor_intelligence.csv": {
                "donor_score",
                "commercial_priority",
                "reported_budget_usd",
                "equipment_specificity",
                "likely_procurement_count",
            },
            "equipment_intelligence.csv": {
                "demand_intensity",
                "evidence_quality",
                "direct_evidence_projects",
                "likely_procurement_count",
                "reported_budget_usd",
            },
            "tender_predictions.csv": {
                "tender_probability",
                "tender_stage",
                "tender_horizon",
                "tender_window",
                "tender_confidence",
            },
            "manufacturer_entities.csv": {
                "manufacturer_entity_id",
                "manufacturer_name",
                "evidence_source",
            },
        }

        for filename, required in expected_headers.items():
            with self.subTest(filename=filename):
                self.assertTrue(required.issubset(csv_header(DATA / filename)))

    def test_sqlite_tables_match_key_csv_counts(self):
        connection = sqlite3.connect(DATA / "iati_intelligence.db")

        try:
            tables = {
                "organisation_entities": "organisation_entities.csv",
                "organisation_aliases": "organisation_aliases.csv",
                "opportunity_scores": "opportunity_scores.csv",
                "donor_intelligence": "donor_intelligence.csv",
                "equipment_intelligence": "equipment_intelligence.csv",
                "tender_predictions": "tender_predictions.csv",
                "target_accounts": "target_accounts.csv",
                "engagements": "engagements.csv",
                "crm_notes": "crm_notes.csv",
                "recommended_actions": "recommended_actions.csv",
            }

            for table, filename in tables.items():
                with self.subTest(table=table):
                    db_count = connection.execute(
                        f"select count(*) from {table}"
                    ).fetchone()[0]
                    self.assertEqual(db_count, csv_count(DATA / filename))
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
