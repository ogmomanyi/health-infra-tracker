from organisation_resolution.duplicate_detector import (
    find_duplicate_candidates
)


def test_find_duplicate_candidates():

    entities = [
        {
            "entity_id": "ORG-001",
            "canonical_name": "World Health Organization"
        },
        {
            "entity_id": "ORG-002",
            "canonical_name": "World Health Organisation"
        },
        {
            "entity_id": "ORG-003",
            "canonical_name": "United Nations"
        }
    ]

    results = find_duplicate_candidates(
        entities,
        threshold=0.90
    )

    assert len(results) == 1

    assert results[0]["entity_a"] == "ORG-001"
    assert results[0]["entity_b"] == "ORG-002"

    assert results[0]["similarity"] >= 0.90