#!/usr/bin/env python3

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DATASETS = {
    "target_accounts.csv",
    "recommended_actions.csv",
    "engagements.csv",
    "crm_notes.csv",
}


class PublicDashboardTests(unittest.TestCase):
    def test_public_artifact_excludes_private_commercial_datasets(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "site"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_public_dashboard.py"),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                check=True,
            )

            published = {path.name for path in (output / "data").iterdir()}
            self.assertTrue(PRIVATE_DATASETS.isdisjoint(published))
            self.assertTrue((output / ".nojekyll").exists())

            config = json.loads(
                (output / "data" / "dashboard_config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(config["mode"], "public")
            self.assertFalse(config["private_datasets"])

            summary = json.loads(
                (output / "data" / "market_summary.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("commercial", summary["layer_counts"])
            self.assertNotIn(
                "COMMERCIAL",
                {layer["layer"] for layer in summary["pipeline_layers"]},
            )
            self.assertNotIn("04", {item["id"] for item in summary["plan_progress"]})

    def test_pages_workflow_uses_the_scoped_builder(self):
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("scripts/build_public_dashboard.py", workflow)
        self.assertIn("actions/upload-pages-artifact@v4", workflow)
        self.assertNotIn("find data", workflow)
        for name in PRIVATE_DATASETS:
            self.assertNotIn(name, workflow)


if __name__ == "__main__":
    unittest.main()
