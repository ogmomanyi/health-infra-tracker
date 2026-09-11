"""Deterministic commercial bid-preparation guidance from existing evidence."""
from __future__ import annotations

from datetime import date
from typing import Iterable


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _upper(value: object) -> str:
    return _text(value).upper()


def build_guidance(
    opportunity: dict[str, object],
    technical_fit: Iterable[dict[str, object]] = (),
    commercial_memory: Iterable[dict[str, object]] = (),
    *,
    today: date | None = None,
) -> dict[str, object]:
    """Return explainable commercial preparation signals; never writes CRM state."""
    today = today or date.today()
    technical = list(technical_fit)
    memory = list(commercial_memory)

    statuses = {
        _upper(row.get("technical_status"))
        for row in technical
        if _text(row.get("technical_status"))
    }
    technical_status = (
        "FAIL"
        if "FAIL" in statuses
        else "REVIEW"
        if "REVIEW" in statuses
        else "UNKNOWN"
        if "UNKNOWN" in statuses
        else "PASS"
        if statuses and statuses <= {"PASS"}
        else "NO_EVIDENCE"
    )

    urgency = _upper(opportunity.get("closing_urgency") or opportunity.get("urgency"))
    closing = _text(opportunity.get("closing_date"))
    if closing:
        try:
            days = (date.fromisoformat(closing[:10]) - today).days
            urgency = "URGENT" if days <= 3 else "SOON" if days <= 14 else "NORMAL"
        except ValueError:
            pass

    catalogue = _upper(opportunity.get("catalogue_fit_status"))
    territory = _upper(opportunity.get("territory_fit"))
    principal = _upper(opportunity.get("principal_status"))
    family = _text(opportunity.get("product_family")).casefold()
    matched = [
        row
        for row in memory
        if _text(row.get("product_family")).casefold() == family
        and _upper(row.get("representation_signal"))
        not in {"EXTERNAL_ONLY", "COMPETITIVE_REFERENCE"}
    ]
    outcomes = {_upper(row.get("outcome")) for row in matched}

    reasons: list[str] = []
    actions: list[str] = []
    posture = "PREPARE_FOR_BID_REVIEW"

    if technical_status == "FAIL":
        posture = "HOLD_FOR_TECHNICAL_RESOLUTION"
        reasons.append("Technical fit contains an explicit failure.")
        actions.append(
            "Resolve the failed specification or identify an approved compliant alternative before pricing."
        )
    elif technical_status in {"UNKNOWN", "REVIEW", "NO_EVIDENCE"}:
        posture = "EVIDENCE_REVIEW_REQUIRED"
        reasons.append("Technical evidence is incomplete or requires review.")
        actions.append(
            "Obtain and verify missing tender/product specifications before treating the candidate as compliant."
        )

    if catalogue in {"FAIL", "NO_MATCH", "UNKNOWN"}:
        reasons.append("Catalogue fit is not confirmed.")
        actions.append(
            "Confirm the Faram catalogue record and product identity before requesting a quote."
        )
    if territory in {"NO", "UNKNOWN", "NOT_CONFIRMED"}:
        reasons.append("Territory authorization is not confirmed.")
        actions.append("Confirm current territory authorization with the principal.")
    if principal in {"INACTIVE", "UNKNOWN", "NOT_CONFIRMED"}:
        reasons.append("Principal status is not confirmed as active.")
        actions.append("Verify current principal status and tender authorization.")

    if matched:
        actions.append(
            f"Use {len(matched)} historical commercial record(s) as negotiation/context evidence, not as current pricing."
        )
        if "ORDERED" in outcomes:
            reasons.append("Historical evidence includes a transaction for this product family.")
        elif outcomes & {"QUOTED", "TENDER_SUPPORT"}:
            reasons.append(
                "Historical quotation/tender-support evidence exists for this product family."
            )
    else:
        actions.append(
            "No directly matched historical commercial memory was found; establish a fresh supplier/pricing baseline."
        )

    if urgency == "URGENT":
        reasons.append("Closing window is urgent.")
        actions.append(
            "Confirm supplier lead time, stock, quotation validity and internal approval path immediately."
        )
    elif urgency == "SOON":
        actions.append(
            "Confirm supplier response time and quotation validity before the closing window tightens."
        )

    if (
        technical_status == "PASS"
        and catalogue not in {"FAIL", "NO_MATCH"}
        and territory not in {"NO", "UNKNOWN", "NOT_CONFIRMED"}
    ):
        posture = "PROCEED_TO_COMMERCIAL_REVIEW"

    return {
        "commercial_posture": posture,
        "technical_status": technical_status,
        "closing_urgency": urgency or "UNKNOWN",
        "historical_memory_count": len(matched),
        "historical_outcomes": sorted(outcomes),
        "historical_evidence_ids": [
            _text(row.get("evidence_id"))
            for row in matched
            if _text(row.get("evidence_id"))
        ],
        "reasons": reasons,
        "preparation_actions": list(dict.fromkeys(actions)),
        "pricing_guidance": (
            "Do not infer a current selling price from historical evidence; obtain a current supplier quote and apply Faram commercial policy."
        ),
    }
