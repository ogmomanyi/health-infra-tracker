from organisation_resolution.resolver import (
    resolve_organisation
)


def test_resolve_existing_organisation():

    candidates = [

        {
            "entity_id":
                "ORG-001",

            "canonical_name":
                "World Health Organization",

            "normalized_name":
                "world health organization"
        }
    ]


    organisation = {

        "organisation_key":
            "REF:WHO",

        "org_ref":
            "WHO",

        "org_name":
            "World Health Organization"
    }


    result = resolve_organisation(
        organisation,
        candidates
    )


    assert result["entity_id"] == "ORG-001"

    assert result["resolution_action"] == "MATCHED"



def test_unresolved_organisation():

    candidates = []


    organisation = {

        "organisation_key":
            "REF:UNKNOWN",

        "org_name":
            "Some Unknown Organisation"
    }


    result = resolve_organisation(
        organisation,
        candidates
    )


    assert result["resolution_action"] == "UNRESOLVED"