"""
Organisation Matching Engine

Responsible for matching normalized organisation names
against existing canonical entities and aliases.
"""

from difflib import SequenceMatcher


def similarity_score(a: str, b: str) -> float:
    """
    Calculate similarity between two strings.
    """

    return SequenceMatcher(
        None,
        a.lower(),
        b.lower()
    ).ratio()


def exact_match(normalized_name, candidates):
    """
    Exact normalized name matching.

    candidates:
        list of dictionaries:
        {
            "entity_id": "...",
            "canonical_name": "...",
            "normalized_name": "..."
        }
    """

    for candidate in candidates:

        if normalized_name == candidate["normalized_name"]:

            return {
                "entity_id": candidate["entity_id"],
                "match_method": "EXACT_MATCH",
                "confidence_score": 1.0
            }

    return None


def fuzzy_match(
    normalized_name,
    candidates,
    threshold=0.85
):
    """
    Fuzzy organisation matching.
    """

    best_match = None
    best_score = 0


    for candidate in candidates:

        score = similarity_score(
            normalized_name,
            candidate["normalized_name"]
        )


        if score > best_score:

            best_score = score
            best_match = candidate


    if best_score >= threshold:

        return {
            "entity_id": best_match["entity_id"],
            "match_method": "FUZZY_MATCH",
            "confidence_score": round(best_score, 3)
        }


    return None


def match_organisation(
    normalized_name,
    candidates
):
    """
    Main matching pipeline.

    Priority:
    1. Exact match
    2. Fuzzy match
    """

    result = exact_match(
        normalized_name,
        candidates
    )


    if result:
        return result


    result = fuzzy_match(
        normalized_name,
        candidates
    )


    return result