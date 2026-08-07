from organisation_resolution.duplicate_detector import (
    find_duplicate_candidates
)


def test_duplicate_detection():

    entities = [
        {
            "entity_id": "ORG001",
            "canonical_name":
            "world health organization"
        },
        {
            "entity_id": "ORG002",
            "canonical_name":
            "world health organisation"
        },
        {
            "entity_id": "ORG003",
            "canonical_name":
            "ministry of health kenya"
        }
    ]


    results = find_duplicate_candidates(
        entities,
        threshold=0.85
    )


    assert len(results) == 1

    assert (
        results[0]["entity_a"]
        ==
        "ORG001"
    )