from procurement_intelligence.historical_scoring import apply_historical_familiarity


def test_historical_familiarity_is_additive_and_capped():
    row = {
        "project_title": "SpectraMax i3x procurement",
        "description": "Laboratory equipment",
        "product_family": "Multimode Microplate Reader",
        "manufacturer_mentions": "Molecular Devices",
    }
    evidence = [
        {
            "evidence_id": "HQE-016",
            "product_family": "Multimode Microplate Reader",
            "product_name": "SpectraMax i3x",
            "manufacturer_name": "Molecular Devices",
            "model": "i3x",
            "evidence_type": "quotation_and_tender_support",
        }
    ]
    result = apply_historical_familiarity(
        row,
        {"opportunity_score": 90, "priority_band": "Strategic Priority", "signal_summary": "equipment demand"},
        evidence,
    )

    assert result["opportunity_score"] == 100.0
    assert result["priority_band"] == "Strategic Priority"
    assert "historical Faram commercial familiarity" in result["signal_summary"]


def test_no_historical_match_does_not_change_score():
    row = {
        "project_title": "Road construction",
        "description": "Civil works",
        "product_family": "",
        "manufacturer_mentions": "",
    }
    result = apply_historical_familiarity(
        row,
        {"opportunity_score": 55, "priority_band": "Watchlist", "signal_summary": "reported budget"},
        [],
    )

    assert result["opportunity_score"] == 55.0
    assert result["priority_band"] == "Watchlist"
    assert result["signal_summary"] == "reported budget"
