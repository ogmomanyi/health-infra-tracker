"""
Organisation Duplicate Detection Engine

Finds potentially duplicate canonical entities.
"""

from organisation_resolution.scoring import name_similarity


def find_duplicate_candidates(
    entities,
    threshold=0.85
):
    """
    Compare organisation entities.

    entities format:

    [
        {
            "entity_id": "...",
            "canonical_name": "..."
        }
    ]

    """

    duplicates = []

    for i, entity_a in enumerate(entities):

        for entity_b in entities[i + 1:]:

            score = name_similarity(
                entity_a["canonical_name"],
                entity_b["canonical_name"]
            )

            if score >= threshold:

                duplicates.append(
                    {
                        "entity_a":
                            entity_a["entity_id"],

                        "entity_b":
                            entity_b["entity_id"],

                        "name_a":
                            entity_a["canonical_name"],

                        "name_b":
                            entity_b["canonical_name"],

                        "similarity":
                            score
                    }
                )

    return duplicates