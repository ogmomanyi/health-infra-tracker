from organisation_resolution.scoring import (
    name_similarity,
    calculate_match_score,
    classify_confidence
)


def test_exact_name_similarity():

    score = name_similarity(
        "world health organization",
        "world health organization"
    )

    assert score == 1.0


def test_similar_name_score():

    score = calculate_match_score(
        "world health organization",
        "world health organisation",
        True,
        True
    )

    assert score > 0.95


def test_confidence_classification():

    assert (
        classify_confidence(0.98)
        ==
        "HIGH_CONFIDENCE"
    )

    assert (
        classify_confidence(0.80)
        ==
        "MEDIUM_CONFIDENCE"
    )

    assert (
        classify_confidence(0.50)
        ==
        "LOW_CONFIDENCE"
    )