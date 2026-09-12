#!/usr/bin/env python3

import argparse
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PUBLIC_CONFIG = ROOT / "deployment" / "public_dashboard_config.json"

PUBLIC_DATASETS = (
    "programme_intelligence.csv",
    "opportunities.csv",
    "opportunity_organisation_resolution.csv",
    "organisation_entities.csv",
    "organisation_aliases.csv",
    "organisation_intelligence.csv",
    "donor_intelligence.csv",
    "equipment_intelligence.csv",
    "product_intelligence.csv",
    "manufacturer_intelligence.csv",
    "tender_predictions.csv",
)

PRIVATE_DATASETS = {
    "target_accounts.csv",
    "recommended_actions.csv",
    "engagements.csv",
    "crm_notes.csv",
    "procurement_document_evidence.csv",
    "procurement_source_collection.csv",
    "procurement_source_health.csv",
}


def public_summary(source: Path, destination: Path) -> None:
    summary = json.loads(source.read_text(encoding="utf-8"))
    summary.get("layer_counts", {}).pop("commercial", None)
    summary["pipeline_layers"] = [
        layer
        for layer in summary.get("pipeline_layers", [])
        if layer.get("layer") != "COMMERCIAL"
    ]
    summary["plan_progress"] = [
        item
        for item in summary.get("plan_progress", [])
        if item.get("id") != "04"
    ]
    destination.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def build(output: Path) -> None:
    output = output.resolve()
    protected = {ROOT.resolve(), DATA_DIR.resolve(), Path.home().resolve()}
    if output in protected:
        raise ValueError(f"Refusing to replace protected directory: {output}")

    if output.exists():
        shutil.rmtree(output)

    output_data = output / "data"
    output_data.mkdir(parents=True)
    shutil.copy2(ROOT / "index.html", output / "index.html")
    shutil.copy2(PUBLIC_CONFIG, output_data / "dashboard_config.json")

    for name in PUBLIC_DATASETS:
        shutil.copy2(DATA_DIR / name, output_data / name)

    public_summary(DATA_DIR / "market_summary.json", output_data / "market_summary.json")
    (output / ".nojekyll").touch()

    published_names = {path.name for path in output_data.iterdir() if path.is_file()}
    exposed = published_names.intersection(PRIVATE_DATASETS)
    if exposed:
        raise RuntimeError(f"Private datasets entered the public artifact: {sorted(exposed)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the privacy-scoped public dashboard.")
    parser.add_argument("--output", type=Path, default=ROOT / "site")
    return parser.parse_args()


if __name__ == "__main__":
    build(parse_args().output)
