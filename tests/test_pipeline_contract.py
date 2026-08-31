import csv
from pathlib import Path


DATA = Path("data")


def read_rows(filename):
    with (DATA / filename).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_donor_scoring_contract():
    rows = read_rows("donor_intelligence.csv")
    assert rows
    values = [float(row["donor_score"]) for row in rows if row.get("donor_score", "")]
    assert values
    assert all(0 <= value <= 100 for value in values)


def test_equipment_scoring_contract():
    rows = read_rows("equipment_intelligence.csv")
    assert rows
    values = [float(row["demand_intensity"]) for row in rows if row.get("demand_intensity", "")]
    assert values
    assert all(0 <= value <= 100 for value in values)
    categories = {row["equipment_category"] for row in rows}
    assert len(categories) == len(rows)


def test_tender_prediction_contract():
    rows = read_rows("tender_predictions.csv")
    assert rows
    values = [float(row["tender_probability"]) for row in rows if row.get("tender_probability", "")]
    assert values
    assert all(0 <= value <= 100 for value in values)
    assert all(row.get("tender_stage") for row in rows)


def test_intelligence_manifest_contract():
    import json

    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["pipeline_version"] == "3.2-project-detail-intelligence"
    for name in (
        "opportunity_scores",
        "donor_intelligence",
        "equipment_intelligence",
        "tender_predictions",
    ):
        assert name in manifest["files"]
