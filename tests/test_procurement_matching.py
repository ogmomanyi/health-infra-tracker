from procurement_intelligence.matcher import match_event
from procurement_intelligence.schema import ProcurementEvent


def event(**overrides):
    values = {
        "procurement_event_id": "proc_test",
        "source": "World Bank",
        "source_url": "https://example.test",
        "tender_reference": "KE-TEST-001",
        "title": "Supply and delivery of laboratory equipment and diagnostic reagents",
        "buyer": "Kenya Medical Supplies Authority",
        "country": "Kenya",
        "publication_date": "2026-09-01",
        "closing_date": "2026-09-30",
        "equipment_category": "Laboratory Equipment",
        "product_family": "Diagnostics",
        "estimated_value": "100000",
        "currency": "USD",
        "matched_iati_identifier": "",
        "match_confidence": 0.0,
        "match_status": "UNMATCHED",
        "project_reference": "",
        "procurement_stage": "Request for Bids",
        "procurement_priority": "HIGH",
        "opportunity_status": "ACTIVE_OPPORTUNITY",
        "faram_relevance_score": 90.0,
        "faram_relevance_reason": "",
    }
    values.update(overrides)
    return ProcurementEvent(**values)


def test_exact_world_bank_project_reference_is_confirmed():
    result = match_event(
        event(project_reference="P179698"),
        [{"iati_identifier": "P179698", "project_title": "Unrelated title"}],
    )
    assert result == {
        "matched_iati_identifier": "P179698",
        "match_confidence": 100.0,
        "match_status": "CONFIRMED",
    }


def test_country_and_equipment_evidence_can_surface_a_possible_match():
    result = match_event(
        event(),
        [{
            "iati_identifier": "XM-DAC-001",
            "project_title": "Kenya laboratory diagnostics strengthening",
            "country_names": "Kenya",
            "equipment_target_summary": "Laboratory Equipment; Diagnostics",
            "funding_agencies": "Ministry of Health",
        }],
    )
    assert result["matched_iati_identifier"] == "XM-DAC-001"
    assert result["match_status"] in {"POSSIBLE", "CONFIRMED"}
    assert result["match_confidence"] >= 65.0


def test_tied_candidates_are_not_forced_into_a_match():
    projects = [
        {
            "iati_identifier": "A",
            "project_title": "Kenya laboratory diagnostics programme",
            "country_names": "Kenya",
            "equipment_target_summary": "Laboratory Equipment; Diagnostics",
            "funding_agencies": "",
        },
        {
            "iati_identifier": "B",
            "project_title": "Kenya laboratory diagnostics programme",
            "country_names": "Kenya",
            "equipment_target_summary": "Laboratory Equipment; Diagnostics",
            "funding_agencies": "",
        },
    ]
    result = match_event(event(), projects)
    assert result["matched_iati_identifier"] == ""
    assert result["match_status"] == "UNMATCHED"
    assert result["match_confidence"] >= 65.0


def test_explicit_iati_identifier_remains_confirmed():
    result = match_event(
        event(matched_iati_identifier="IATI-123"),
        [{"iati_identifier": "IATI-123", "project_title": "Anything"}],
    )
    assert result["match_status"] == "CONFIRMED"
    assert result["match_confidence"] == 100.0
