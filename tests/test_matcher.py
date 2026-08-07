from organisation_resolution.matcher import (
    similarity_score,
    match_organisation
)


def test_similarity():

    score = similarity_score(
        "world health organization",
        "world health organisation"
    )

    assert score > 0.9



def test_exact_match():

    candidates = [
        {
            "entity_id": "ORG-001",
            "canonical_name":
                "World Health Organization",
            "normalized_name":
                "world health organization"
        }
    ]


    result = match_organisation(
        "world health organization",
        candidates
    )


    assert result["entity_id"] == "ORG-001"
    assert result["match_method"] == "EXACT_MATCH"