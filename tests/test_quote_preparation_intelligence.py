from datetime import date

from procurement_intelligence.quote_preparation_intelligence import build_guidance


def opportunity(**overrides):
    base = {
        "product_family": "Analyzer",
        "currency": "KES",
        "estimated_value": "1000000",
    }
    base.update(overrides)
    return base


def execution(*responses, decision="BID"):
    return {
        "bid_decision": {"decision": decision},
        "responses": list(responses),
    }


def test_missing_quote_requests_fresh_supplier_quote():
    result = build_guidance(
        opportunity(),
        execution(),
        [],
        today=date(2026, 9, 11),
    )
    assert result["quote_preparation_posture"] == "REQUEST_CURRENT_SUPPLIER_QUOTE"
    assert result["quote_status"] == "MISSING"
    assert result["canonical_priority_is_unchanged"] is True


def test_current_quote_is_ready_for_internal_pricing_review():
    result = build_guidance(
        opportunity(),
        execution(
            {
                "response_type": "QUOTE",
                "currency": "KES",
                "valid_until": "2026-09-30",
                "status": "RECEIVED",
            }
        ),
        [],
        today=date(2026, 9, 11),
    )
    assert result["quote_preparation_posture"] == "READY_FOR_INTERNAL_PRICING_REVIEW"
    assert result["quote_status"] == "CURRENT"
    assert result["current_quote_count"] == 1


def test_expired_quote_requires_refresh():
    result = build_guidance(
        opportunity(),
        execution(
            {
                "response_type": "QUOTATION",
                "currency": "KES",
                "valid_until": "2026-09-01",
                "status": "RECEIVED",
            }
        ),
        [],
        today=date(2026, 9, 11),
    )
    assert result["quote_preparation_posture"] == "REFRESH_EXPIRED_QUOTE"
    assert result["expired_quote_count"] == 1


def test_currency_mismatch_requires_alignment_not_conversion_guess():
    result = build_guidance(
        opportunity(currency="KES"),
        execution(
            {
                "response_type": "PRICING",
                "currency": "USD",
                "valid_until": "2026-09-30",
                "status": "RECEIVED",
            }
        ),
        [],
        today=date(2026, 9, 11),
    )
    assert result["quote_preparation_posture"] == "ALIGN_QUOTE_CURRENCY"
    assert result["currency_mismatch"] is True
    assert "FX basis" in " ".join(result["preparation_actions"])


def test_human_no_bid_takes_precedence():
    result = build_guidance(
        opportunity(),
        execution(
            {
                "response_type": "QUOTE",
                "currency": "KES",
                "valid_until": "2026-09-30",
                "status": "RECEIVED",
            },
            decision="NO_BID",
        ),
        [],
        today=date(2026, 9, 11),
    )
    assert result["quote_preparation_posture"] == "HOLD_NO_BID"
    assert result["human_bid_decision"] == "NO_BID"


def test_historical_memory_is_context_and_competitor_is_not_inferred():
    memory = [
        {
            "product_family": "Analyzer",
            "representation_signal": "ACTIVE_COMMERCIAL",
            "outcome": "QUOTED",
            "evidence_id": "HQE-1",
            "manufacturer_name": "Faram Principal",
        },
        {
            "product_family": "Analyzer",
            "representation_signal": "COMPETITIVE_REFERENCE",
            "evidence_id": "HQE-2",
            "manufacturer_name": "Competitor A",
        },
    ]
    result = build_guidance(
        opportunity(),
        execution(),
        memory,
        today=date(2026, 9, 11),
    )
    assert result["historical_commercial_context_count"] == 1
    assert result["historical_evidence_ids"] == ["HQE-1"]
    assert result["competitive_reference_names"] == ["Competitor A"]
    assert "Do not infer current supplier cost" in result["pricing_guardrail"]
