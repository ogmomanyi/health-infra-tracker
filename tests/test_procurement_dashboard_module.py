from pathlib import Path


def test_procurement_dashboard_module_is_self_contained():
    path = Path("procurement_intelligence/dashboard.js")
    text = path.read_text(encoding="utf-8")

    assert "External Procurement Intelligence" in text
    assert "procurement_events.csv" in text
    assert "match_confidence" in text
    assert "CONFIRMED" in text
    assert "UNMATCHED" in text


def test_procurement_fixture_has_required_dashboard_fields():
    import csv

    with Path("data/procurement_events.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert rows
    required = {
        "procurement_event_id",
        "source",
        "title",
        "buyer",
        "country",
        "closing_date",
        "matched_iati_identifier",
        "match_confidence",
        "match_status",
        "procurement_stage",
        "procurement_priority",
    }
    assert required.issubset(rows[0])
    assert any(row["match_status"] == "CONFIRMED" for row in rows)
    assert any(row["match_status"] == "UNMATCHED" for row in rows)
