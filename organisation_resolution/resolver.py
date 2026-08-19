"""
Organisation Resolution Pipeline

Combines:
- name normalization
- entity matching

Produces resolution decisions.
"""

from organisation_resolution.normalizer import normalize_name
from organisation_resolution.matcher import match_organisation


def resolve_organisation(
    organisation_record,
    candidates
):
    """
    Resolve a single organisation.

    Input:

    {
        "organisation_key": "...",
        "org_ref": "...",
        "org_name": "..."
    }

    """

    raw_name = organisation_record["org_name"]

    normalized_name = normalize_name(
        raw_name
    )

    match = match_organisation(
        normalized_name,
        candidates
    )


    if match:

        return {
            "organisation_key":
                organisation_record.get(
                    "organisation_key"
                ),

            "org_ref":
                organisation_record.get(
                    "org_ref"
                ),

            "alias_name":
                raw_name,

            "normalized_name":
                normalized_name,

            "entity_id":
                match["entity_id"],

            "match_method":
                match["match_method"],

            "confidence_score":
                match["confidence_score"],

            "resolution_action":
                "MATCHED"
        }


    return {

        "organisation_key":
            organisation_record.get(
                "organisation_key"
            ),

        "org_ref":
            organisation_record.get(
                "org_ref"
            ),

        "alias_name":
            raw_name,

        "normalized_name":
            normalized_name,

        "entity_id":
            None,

        "match_method":
            None,

        "confidence_score":
            0,

        "resolution_action":
            "UNRESOLVED"
    }