from procurement_intelligence.manufacturer_relationships import build_manufacturer_relationships


def fixtures(match_status="CONFIRMED", notice_text=""):
    matches = [{
        "procurement_event_id": "E1", "product_family": "Hematology Analyzer",
        "manufacturer_names": "Sysmex", "manufacturer_entity_ids": "M1",
        "model_evidence": "XN-1000",
    }]
    events = [{
        "procurement_event_id": "E1", "buyer": "Ministry of Health", "country": "Kenya",
        "opportunity_status": "AWARD_HISTORY", "match_status": match_status,
        "matched_iati_identifier": "IATI-1", "publication_date": "2026-08-01",
        "tender_reference": "T-1", "source_url": "https://example.test/1",
        "notice_text": notice_text,
    }]
    opportunities = [{
        "iati_identifier": "IATI-1", "funding_agencies": "Global Fund",
        "implementing_partners": "National Laboratory Service", "accountable_orgs": "",
    }]
    buyers = [{
        "buyer": "Ministry of Health", "canonical_buyer": "Ministry of Health",
        "raw_buyer_names": "Ministry of Health", "country": "Kenya", "entity_id": "O-BUYER",
    }]
    resolutions = [
        {"opportunity_id": "IATI-1", "organisation_name": "Global Fund", "organisation_role": "FUNDING", "entity_id": "O-DONOR"},
        {"opportunity_id": "IATI-1", "organisation_name": "National Laboratory Service", "organisation_role": "IMPLEMENTING", "entity_id": "O-RECIPIENT"},
    ]
    accounts = [
        {"target_account_id": "A-BUYER", "organisation_entity_id": "O-BUYER", "account_name": "Ministry of Health"},
        {"target_account_id": "A-DONOR", "organisation_entity_id": "O-DONOR", "account_name": "Global Fund"},
    ]
    manufacturers = [{
        "manufacturer_entity_id": "M1", "manufacturer_name": "Sysmex",
        "manufacturer_aliases": "Sysmex Corporation",
    }]
    return matches, events, opportunities, buyers, resolutions, accounts, manufacturers


def test_confirmed_project_propagates_award_affinity_to_buyer_donor_and_recipient():
    rows = build_manufacturer_relationships(*fixtures())
    assert {row["party_role"] for row in rows} == {"BUYER", "DONOR", "RECEIVING_PARTY"}
    assert all(row["observed_award_count"] == "1" for row in rows)
    assert all(row["relationship_signal"] == "OBSERVED_AWARD_AFFINITY" for row in rows)
    assert next(row for row in rows if row["party_role"] == "DONOR")["target_account_id"] == "A-DONOR"


def test_possible_project_match_does_not_propagate_to_donor_or_recipient():
    rows = build_manufacturer_relationships(*fixtures(match_status="POSSIBLE"))
    assert [row["party_role"] for row in rows] == ["BUYER"]


def test_preference_is_only_claimed_from_explicit_language():
    rows = build_manufacturer_relationships(*fixtures(notice_text="Preferred manufacturer: Sysmex"))
    assert all(row["preference_status"] == "EXPLICIT_SOURCE_PREFERENCE" for row in rows)
    assert all(row["relationship_signal"] == "EXPLICIT_PREFERENCE" for row in rows)


def test_preference_language_does_not_attach_to_an_unrelated_manufacturer():
    matches, events, opportunities, buyers, resolutions, accounts, manufacturers = fixtures(
        notice_text="Preferred manufacturer: Roche"
    )
    rows = build_manufacturer_relationships(
        matches, events, opportunities, buyers, resolutions, accounts, manufacturers
    )
    assert all(row["preference_status"] == "NOT_ESTABLISHED" for row in rows)


def test_explicit_preference_can_come_from_a_linked_document():
    values = fixtures()
    documents = [{
        "procurement_event_id": "E1", "extraction_status": "EXTRACTED",
        "document_text": "The preferred model is XN-1000.",
    }]
    rows = build_manufacturer_relationships(*values, document_evidence=documents)
    assert all(row["preference_status"] == "EXPLICIT_SOURCE_PREFERENCE" for row in rows)


def test_low_relevance_manufacturer_only_notice_is_excluded():
    matches, events, opportunities, buyers, resolutions, accounts, manufacturers = fixtures()
    matches[0].update({"product_family": "", "model_evidence": ""})
    events[0]["faram_relevance_score"] = "25"
    rows = build_manufacturer_relationships(
        matches, events, opportunities, buyers, resolutions, accounts, manufacturers
    )
    assert rows == []


def test_world_bank_project_metadata_attributes_donor_and_receiving_parties():
    matches, events, _, buyers, resolutions, accounts, manufacturers = fixtures(
        match_status="UNMATCHED"
    )
    events[0].update({
        "source": "World Bank", "project_reference": "P173820", "buyer": "",
    })
    metadata = [{
        "project_reference": "P173820", "borrower": "Republic of Kenya",
        "implementing_agency": "Ministry of Health", "fetch_status": "SUCCESS",
    }]
    rows = build_manufacturer_relationships(
        matches, events, [], buyers, resolutions, accounts, manufacturers, metadata
    )
    assert {row["party_role"] for row in rows} == {"DONOR", "RECEIVING_PARTY"}
    assert {row["party_name"] for row in rows} == {
        "World Bank", "Republic of Kenya", "Ministry of Health",
    }
    assert all(row["relationship_signal"] == "OBSERVED_AWARD_AFFINITY" for row in rows)
