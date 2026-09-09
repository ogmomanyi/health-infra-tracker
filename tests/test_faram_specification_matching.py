from procurement_intelligence.faram_specification_matching import assess_candidates, assess_product


def spec(product_id, name, value, unit="", status="VERIFIED"):
    return {
        "faram_product_id": product_id,
        "specification_name": name,
        "specification_value": value,
        "specification_unit": unit,
        "source": "manufacturer datasheet",
        "source_reference": "DOC-001",
        "verification_status": status,
    }


def test_verified_specs_produce_pass():
    result = assess_product(
        "Throughput: 120 tests/hour; Wavelength: 340 nm",
        "F-001",
        [spec("F-001", "Throughput", "150", "tests/hour"), spec("F-001", "Wavelength", "340", "nm")],
    )
    assert result["technical_status"] == "PASS"
    assert result["passed"] == 2
    assert result["unknown"] == 0
    assert result["failed"] == 0


def test_missing_verified_spec_is_unknown_not_fail():
    result = assess_product(
        "Throughput: 120 tests/hour; Capacity: 500 ml",
        "F-001",
        [spec("F-001", "Throughput", "150", "tests/hour")],
    )
    assert result["technical_status"] == "REVIEW"
    assert result["unknown"] == 1
    assert result["failed"] == 0


def test_failed_spec_is_reported():
    result = assess_product(
        "Throughput: 200 tests/hour",
        "F-001",
        [spec("F-001", "Throughput", "150", "tests/hour")],
    )
    assert result["technical_status"] == "FAIL"
    assert result["failed"] == 1


def test_unverified_specification_cannot_create_pass():
    result = assess_product(
        "Throughput: 120 tests/hour",
        "F-001",
        [spec("F-001", "Throughput", "150", "tests/hour", "UNVERIFIED")],
    )
    assert result["technical_status"] == "REVIEW"
    assert result["unknown"] == 1


def test_no_extractable_requirements_remains_unknown():
    result = assess_product("Analyzer required", "F-001", [spec("F-001", "Throughput", "150", "tests/hour")])
    assert result["technical_status"] == "UNKNOWN"
    assert result["requirements_count"] == 0


def test_candidate_assessment_preserves_existing_match_fields():
    candidates = [{"faram_product_id": "F-001", "match_status": "FARAM_MATCH", "match_confidence": 95.0}]
    results = assess_candidates(
        "Throughput: 120 tests/hour",
        candidates,
        [spec("F-001", "Throughput", "150", "tests/hour")],
    )
    assert results[0]["match_status"] == "FARAM_MATCH"
    assert results[0]["match_confidence"] == 95.0
    assert results[0]["technical_status"] == "PASS"
