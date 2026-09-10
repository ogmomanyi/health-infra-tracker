"""Deterministic bid/no-bid guidance from existing opportunity evidence.

This is decision support only. It never writes a CRM decision and never changes
canonical commercial priority.
"""
from __future__ import annotations


def _text(value: object) -> str:
    return " ".join(str(value or "").split()).upper()


def _days(value: object) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def guidance(opportunity: dict[str, object], technical_fit: list[dict[str, object]]) -> dict[str, object]:
    """Return a transparent decision posture and reason codes."""
    reasons: list[str] = []
    statuses = [_text(row.get("technical_status")) for row in technical_fit]
    if technical_fit and all(status == "FAIL" for status in statuses):
        return {"posture": "DO_NOT_BID", "reason_codes": ["TECHNICAL_FAILURE"],
                "summary": "Technical failure identified; do not bid without an approved alternative.",
                "automatic_decision": False}
    if "FAIL" in statuses:
        reasons.append("TECHNICAL_FAILURE_ON_CANDIDATE")
    if "REVIEW" in statuses:
        reasons.append("TECHNICAL_REVIEW_REQUIRED")
    if "UNKNOWN" in statuses or not technical_fit:
        reasons.append("TECHNICAL_EVIDENCE_GAP")

    territory = [_text(row.get("territory_fit")) for row in technical_fit]
    if territory and not any(value in {"YES", "TRUE", "Y"} for value in territory):
        reasons.append("NO_CONFIRMED_TERRITORY_FIT")

    days = _days(opportunity.get("days_to_closing"))
    if days is not None and days < 0:
        reasons.append("CLOSING_DATE_PASSED")
    elif days is not None and days <= 7:
        reasons.append("CLOSING_WITHIN_7_DAYS")

    if "CLOSING_DATE_PASSED" in reasons:
        posture = "HOLD"
        summary = "Closing date has passed; do not proceed until the procurement status is confirmed."
    elif any(code in reasons for code in ("TECHNICAL_REVIEW_REQUIRED", "TECHNICAL_EVIDENCE_GAP", "NO_CONFIRMED_TERRITORY_FIT")):
        posture = "TECHNICAL_REVIEW"
        summary = "Technical/compliance evidence requires review before a bid decision."
    elif "TECHNICAL_FAILURE_ON_CANDIDATE" in reasons:
        posture = "REVIEW_ALTERNATIVE"
        summary = "A candidate has a technical failure; assess an approved alternative before deciding."
    else:
        posture = "PROCEED_TO_BID_REVIEW"
        summary = "Available technical and commercial signals support proceeding to human bid/no-bid review."

    return {"posture": posture, "reason_codes": reasons, "summary": summary, "automatic_decision": False}
