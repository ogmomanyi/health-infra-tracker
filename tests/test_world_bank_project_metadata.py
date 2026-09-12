from procurement_intelligence.world_bank_project_metadata import (
    build_project_metadata,
    relevant_project_references,
)


def test_relevant_references_only_include_world_bank_manufacturer_evidence():
    events = [
        {"procurement_event_id": "E1", "source": "World Bank", "project_reference": "P1"},
        {"procurement_event_id": "E2", "source": "UNDP", "project_reference": "P2"},
    ]
    matches = [
        {"procurement_event_id": "E1", "manufacturer_names": "Abbott"},
        {"procurement_event_id": "E2", "manufacturer_names": "Roche"},
    ]
    assert relevant_project_references(matches, events) == ["P1"]


def test_project_metadata_is_normalized_and_cached():
    calls = []

    def fetcher(reference):
        calls.append(reference)
        return {
            "project_name": "Health Project", "borrower": "Republic of Kenya",
            "impagency": "Ministry of Health", "countryname": ["Republic of Kenya"],
            "url": "https://example.test/P1",
        }

    rows = build_project_metadata(["P1"], fetcher=fetcher, fetched_at="2026-09-12T00:00:00+00:00")
    assert rows[0]["borrower"] == "Republic of Kenya"
    assert rows[0]["implementing_agency"] == "Ministry of Health"
    assert rows[0]["country"] == "Republic of Kenya"
    assert rows[0]["fetch_status"] == "SUCCESS"
    build_project_metadata(["P1"], rows, fetcher=fetcher)
    assert calls == ["P1"]
