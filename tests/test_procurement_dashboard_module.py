from pathlib import Path


def test_procurement_dashboard_module_is_self_contained():
    text = Path("procurement_intelligence/dashboard.js").read_text(encoding="utf-8")
    assert "External Procurement" in text
    assert "procurement_events.csv" in text
    assert "match_confidence" in text
    assert "CONFIRMED" in text
    assert "UNMATCHED" in text
