"""
Organisation Entity Resolution Scoring Engine

Calculates confidence scores between
incoming organisation names and canonical entities.
"""

from difflib import SequenceMatcher


def name_similarity(name_a, name_b):
    """
    Calculate similarity between two names.
    Returns score between 0 and 1.
    """

    if not name_a or not name_b:
        return 0

    return round(
        SequenceMatcher(
            None,
            name_a,
            name_b
        ).ratio(),
        4
    )


def calculate_match_score(
    normalized_name,
    candidate_name,
    reference_match=False,
    country_match=False
):
    """
    Calculate weighted organisation match score.

    Weights:

    Name similarity: 70%
    Reference match: 20%
    Country consistency: 10%
    """

    name_score = name_similarity(
        normalized_name,
        candidate_name
    )

    score = (
        name_score * 0.70
        +
        (1 if reference_match else 0) * 0.20
        +
        (1 if country_match else 0) * 0.10
    )

    return round(score, 4)


def classify_confidence(score):

    if score >= 0.95:
        return "HIGH_CONFIDENCE"

    if score >= 0.75:
        return "MEDIUM_CONFIDENCE"

    return "LOW_CONFIDENCE"