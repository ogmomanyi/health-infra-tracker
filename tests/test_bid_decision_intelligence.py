from __future__ import annotations

from procurement_intelligence.bid_decision_intelligence import build_guidance


def opportunity(**overrides):
    value = {
        "opportunity_id": "OPP-1",
        "procurement_event_id": "EV-1",
        "commercial_account_priority_score": "88.0",
        "commercial_account_priority_tier": "ACT_NOW",
        "catalogue_fit_status": "MATCH",
        "closing_date": "2099-12-31",
    }
    value.update(overrides)
    return value


def test_pass_guidance_recommends_bid_review_without_creating_decision():
    result = build_guidance(opportunity(), [{
        "technical_status": "PASS", "territory_fit": "YES", "principal_status": "ACTIVE",
    }], {"bid_decision": {"decision": "PENDING"}})
    assert result["guidance"] == "PROCEED_TO_BID_REVIEW"
    assert result["human_bid_decision"] == "PENDING"
    assert result["commercial_account_priority_score"] == 88.0
    assert result["commercial_account_priority_tier"] == "ACT_NOW"
    assert result["canonical_priority_is_unchanged"] is True


def test_fail_guidance_does_not_automatically_set_no_bid():
    result = build_guidance(opportunity(), [{"technical_status": "FAIL", "territory_fit": "YES"}], {"bid_decision": {"decision": "PENDING"}})
    assert result["guidance"] == "DO_NOT_BID_TECHNICAL_FAILURE"
    assert result["human_bid_decision"] == "PENDING"


def test_unknown_technical_evidence_is_not_treated_as_failure():
    result = build_guidance(opportunity(), [{"technical_status": "UNKNOWN"}], {"bid_decision": {"decision": "PENDING"}})
    assert result["guidance"] == "HOLD_FOR_TECHNICAL_REVIEW"
    assert result["technical"]["fail"] == 0
    assert result["technical"]["unknown"] == 1


def test_mixed_pass_and_fail_candidates_require_review():
    result = build_guidance(opportunity(), [
        {"technical_status": "PASS", "territory_fit": "YES"},
        {"technical_status": "FAIL", "territory_fit": "YES"},
    ])
    assert result["guidance"] == "HOLD_FOR_TECHNICAL_REVIEW"
    assert result["technical"]["pass"] == 1
    assert result["technical"]["fail"] == 1


def test_existing_human_decision_is_preserved():
    result = build_guidance(opportunity(), [{"technical_status": "PASS"}], {"bid_decision": {"decision": "BID"}})
    assert result["guidance"] == "PROCEED_TO_BID_REVIEW"
    assert result["human_bid_decision"] == "BID"


def test_expired_tender_adds_urgency_reason_without_changing_posture():
    result = build_guidance(opportunity(closing_date="2020-01-01"), [{"technical_status": "PASS"}])
    assert result["guidance"] == "PROCEED_TO_BID_REVIEW"
    assert any("closing date has passed" in reason for reason in result["reasons"])
