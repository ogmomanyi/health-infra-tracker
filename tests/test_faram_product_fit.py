from procurement_intelligence.faram_product_fit import build_product_fit


CANDIDATE = {
    "procurement_event_id": "EV-1",
    "tender_reference": "T-1",
    "faram_product_id": "F-1",
    "product_name": "Analyzer A",
    "manufacturer_name": "Principal A",
    "match_status": "FARAM_MATCH",
    "match_confidence": "95.0",
    "territory_fit": "YES",
}


FARAM_SPECS = [
    {
        "faram_product_id": "F-1",
        "specification_name": "throughput",
        "specification_value": "100",
        "specification_unit": "tests/hour",
        "source": "datasheet",
        "source_reference": "DS-1",
        "verification_status": "VERIFIED",
    }
]


def requirement(status="VERIFIED", value="80"):
    return {
        "procurement_event_id": "EV-1",
        "specification_name": "throughput",
        "specification_value": value,
        "specification_unit": "tests/hour",
        "source": "tender",
        "source_reference": "T-1",
        "verification_status": status,
    }


def test_product_fit_passes_verified_requirement():
    rows = build_product_fit([CANDIDATE], [requirement()], FARAM_SPECS)
    assert rows[0]["technical_status"] == "PASS"
    assert rows[0]["technical_passed"] == 1
    assert rows[0]["technical_unknown"] == 0
    assert rows[0]["technical_failed"] == 0
    assert rows[0]["match_confidence"] == "95.0"


def test_product_fit_is_unknown_without_tender_evidence():
    rows = build_product_fit([CANDIDATE], [], FARAM_SPECS)
    assert rows[0]["technical_status"] == "UNKNOWN"
    assert rows[0]["technical_score"] == 0.0


def test_product_fit_fails_explicitly_incompatible_requirement():
    rows = build_product_fit([CANDIDATE], [requirement(value="120")], FARAM_SPECS)
    assert rows[0]["technical_status"] == "FAIL"
    assert rows[0]["technical_failed"] == 1


def test_unverified_tender_requirement_is_not_matchable():
    rows = build_product_fit([CANDIDATE], [requirement(status="UNVERIFIED")], FARAM_SPECS)
    assert rows[0]["technical_status"] == "UNKNOWN"
    assert rows[0]["technical_unknown"] == 0
