"""Build read-only bid/no-bid guidance from existing opportunity evidence.

This module is decision support only. It never writes the human bid decision and
never recalculates the canonical commercial account priority score.
"""
from __future__ import annotations

from datetime import date


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _number(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _closing_days(value: object) -> int | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        return (date.fromisoformat(raw) - date.today()).days
    except ValueError:
        try:
            return int(float(raw))
        except ValueError:
            return None


def _technical_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    statuses = {_text(row.get("technical_status")).upper() or "UNKNOWN" for row in rows}
    if not rows:
        return {"status": "UNKNOWN", "candidate_count": 0, "pass": 0, "review": 0, "fail": 0, "unknown": 0}
    return {
        "status": "FAIL" if "FAIL" in statuses else "REVIEW" if "REVIEW" in statuses else "PASS" if "PASS" in statuses else "UNKNOWN",
        "candidate_count": len(rows),
        "pass": sum(_text(r.get("technical_status")).upper() == "PASS" for r in rows),
        "review": sum(_text(r.get("technical_status")).upper() == "REVIEW" for r in rows),
        "fail": sum(_text(r.get("technical_status")).upper() == "FAIL" for r in rows),
        "unknown": sum(_text(r.get("technical_status")).upper() == "UNKNOWN" for r in rows),
    }


def build_guidance(opportunity: dict[str, object], technical_fit: list[dict[str, object]], execution: dict[str, object] | None = None) -> dict[str, object]:
    """Return evidence-based posture without changing CRM state."""
    technical = _technical_summary(technical_fit)
    catalogue_status = _text(opportunity.get("catalogue_fit_status")).upper() or "UNKNOWN"
    territory_values = {_text(r.get("territory_fit")).upper() for r in technical_fit if _text(r.get("territory_fit"))}
    territory_fit = "YES" if "YES" in territory_values else "NO" if territory_values and territory_values == {"NO"} else "UNKNOWN"
    principal_values = {_text(r.get("principal_status")).upper() for r in technical_fit if _text(r.get("principal_status"))}
    principal_status = "ACTIVE" if "ACTIVE" in principal_values else "UNKNOWN"
    days = _closing_days(opportunity.get("closing_date"))

    reasons: list[str] = []
    if technical["status"] == "FAIL":
        posture = "DO_NOT_BID_TECHNICAL_FAILURE"
        reasons.append("At least one matched Faram candidate has a verified technical failure.")
    elif technical["status"] in {"REVIEW", "UNKNOWN"}:
        posture = "HOLD_FOR_TECHNICAL_REVIEW"
        reasons.append("Verified technical evidence is incomplete or requires review before bid/no-bid.")
    elif territory_fit == "NO":
        posture = "HOLD_FOR_TERRITORY_REVIEW"
        reasons.append("Available Faram candidate evidence does not support territory fit.")
    elif catalogue_status in {"NO_MATCH", "FAIL"}:
        posture = "HOLD_FOR_CATALOGUE_REVIEW"
        reasons.append("The catalogue match does not currently support a compliant product route.")
    else:
        posture = "PROCEED_TO_BID_REVIEW"
        reasons.append("Technical fit is supported by verified evidence; proceed to commercial bid review.")

    if days is not None and days < 0:
        reasons.append("Tender closing date has passed; confirm whether the opportunity is still actionable.")
    elif days is not None and days <= 7:
        reasons.append(f"Tender closes in {days} day(s); decision requires prompt ownership.")

    decision = "PENDING"
    if execution:
        bid = execution.get("bid_decision")
        if isinstance(bid, dict):
            decision = _text(bid.get("decision")).upper() or "PENDING"

    score = _number(opportunity.get("commercial_account_priority_score"))
    tier = _text(opportunity.get("commercial_account_priority_tier"))
    return {
        "guidance": posture,
        "guidance_label": {
            "PROCEED_TO_BID_REVIEW": "PROCEED TO BID REVIEW",
            "HOLD_FOR_TECHNICAL_REVIEW": "TECHNICAL REVIEW REQUIRED",
            "DO_NOT_BID_TECHNICAL_FAILURE": "DO NOT BID — TECHNICAL FAILURE",
            "HOLD_FOR_TERRITORY_REVIEW": "TERRITORY REVIEW REQUIRED",
            "HOLD_FOR_CATALOGUE_REVIEW": "CATALOGUE REVIEW REQUIRED",
        }[posture],
        "reasons": reasons,
        "technical": technical,
        "catalogue_fit_status": catalogue_status,
        "territory_fit": territory_fit,
        "principal_status": principal_status,
        "days_to_closing": days,
        "commercial_account_priority_score": score,
        "commercial_account_priority_tier": tier,
        "human_bid_decision": decision,
        "decision_is_mutable_crm_state": True,
        "canonical_priority_is_unchanged": True,
    }
