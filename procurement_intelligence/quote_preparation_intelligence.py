"""Deterministic quote and pricing-preparation intelligence.

This layer evaluates whether an opportunity has enough current commercial evidence
for internal pricing review. It never infers current supplier cost, selling price,
margin, or canonical commercial priority.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable, Mapping


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _upper(value: object) -> str:
    return _text(value).upper()


def _parse_date(value: object) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _is_quote(row: Mapping[str, object]) -> bool:
    response_type = _upper(row.get("response_type"))
    return any(token in response_type for token in ("QUOTE", "QUOTATION", "PRICING"))


def _quote_state(
    responses: Iterable[Mapping[str, object]],
    *,
    today: date,
) -> tuple[str, list[dict[str, object]], list[dict[str, object]]]:
    quotes = [dict(row) for row in responses if _is_quote(row)]
    if not quotes:
        return "MISSING", [], []

    live: list[dict[str, object]] = []
    expired: list[dict[str, object]] = []
    for row in quotes:
        valid_until = _parse_date(row.get("valid_until"))
        status = _upper(row.get("status"))
        if status in {"CANCELLED", "REJECTED", "VOID"}:
            continue
        if valid_until and valid_until < today:
            expired.append(row)
        else:
            live.append(row)

    if live:
        return "CURRENT", live, expired
    if expired:
        return "EXPIRED", [], expired
    return "MISSING", [], []


def build_guidance(
    opportunity: Mapping[str, object],
    execution: Mapping[str, object] | None = None,
    commercial_memory: Iterable[Mapping[str, object]] = (),
    *,
    today: date | None = None,
) -> dict[str, object]:
    """Return explainable quote-preparation guidance without mutating CRM state."""
    today = today or date.today()
    execution = execution or {}
    responses = list(execution.get("responses") or [])
    bid_decision = dict(execution.get("bid_decision") or {})
    memory = list(commercial_memory)

    quote_status, current_quotes, expired_quotes = _quote_state(responses, today=today)
    human_bid_decision = _upper(bid_decision.get("decision")) or "PENDING"

    opportunity_currency = _upper(opportunity.get("currency"))
    estimated_value = opportunity.get("estimated_value")
    current_quote_currencies = sorted(
        {
            _upper(row.get("currency"))
            for row in current_quotes
            if _upper(row.get("currency"))
        }
    )
    currency_mismatch = bool(
        opportunity_currency
        and current_quote_currencies
        and opportunity_currency not in current_quote_currencies
    )

    product_family = _text(opportunity.get("product_family")).casefold()
    historical = [
        row
        for row in memory
        if _text(row.get("product_family")).casefold() == product_family
        and _upper(row.get("representation_signal"))
        not in {"EXTERNAL_ONLY", "COMPETITIVE_REFERENCE"}
    ]
    competitive = [
        row
        for row in memory
        if _text(row.get("product_family")).casefold() == product_family
        and _upper(row.get("representation_signal")) == "COMPETITIVE_REFERENCE"
    ]
    competitor_names = sorted(
        {
            _text(row.get("manufacturer_name"))
            for row in competitive
            if _text(row.get("manufacturer_name"))
        }
    )

    reasons: list[str] = []
    actions: list[str] = []
    posture = "REQUEST_CURRENT_SUPPLIER_QUOTE"

    if human_bid_decision == "NO_BID":
        posture = "HOLD_NO_BID"
        reasons.append("The human CRM decision is NO_BID.")
        actions.append(
            "Do not prepare a commercial submission unless the human bid decision is explicitly changed."
        )
    elif quote_status == "MISSING":
        reasons.append("No current supplier quotation or pricing response is recorded.")
        actions.append(
            "Obtain a current supplier/principal quotation with currency, validity, lead time and commercial terms."
        )
    elif quote_status == "EXPIRED":
        posture = "REFRESH_EXPIRED_QUOTE"
        reasons.append("Only expired supplier quotation evidence is available.")
        actions.append(
            "Refresh the supplier quotation before using it for internal pricing or tender submission."
        )
    else:
        posture = "READY_FOR_INTERNAL_PRICING_REVIEW"
        reasons.append("A non-expired supplier quotation or pricing response is recorded.")

    if currency_mismatch:
        posture = (
            posture
            if posture in {"HOLD_NO_BID", "REFRESH_EXPIRED_QUOTE"}
            else "ALIGN_QUOTE_CURRENCY"
        )
        reasons.append(
            "The current supplier quote currency does not match the opportunity currency."
        )
        actions.append(
            "Confirm the approved FX basis and quote currency before margin or selling-price approval."
        )

    if estimated_value not in (None, ""):
        actions.append(
            "Confirm payment terms, financing cost, freight, taxes/clearing responsibilities and validity before margin approval."
        )
    else:
        actions.append(
            "Record the opportunity value or commercial basis before final internal pricing approval."
        )

    if historical:
        actions.append(
            f"Use {len(historical)} historical commercial record(s) as negotiation context only; do not reuse historical prices as current cost."
        )
    else:
        actions.append(
            "No matched historical commercial context is available; build the quote from fresh supplier evidence."
        )

    if competitor_names:
        reasons.append(
            "Historical competitive-reference evidence exists for this product family."
        )
        actions.append(
            "Review the named competitive references as context only; do not assume they are bidding on this opportunity."
        )

    return {
        "quote_preparation_posture": posture,
        "quote_status": quote_status,
        "human_bid_decision": human_bid_decision,
        "current_quote_count": len(current_quotes),
        "expired_quote_count": len(expired_quotes),
        "current_quote_currencies": current_quote_currencies,
        "opportunity_currency": opportunity_currency or "UNKNOWN",
        "estimated_value": estimated_value,
        "currency_mismatch": currency_mismatch,
        "historical_commercial_context_count": len(historical),
        "historical_evidence_ids": [
            _text(row.get("evidence_id"))
            for row in historical
            if _text(row.get("evidence_id"))
        ],
        "competitive_reference_names": competitor_names,
        "reasons": reasons,
        "preparation_actions": list(dict.fromkeys(actions)),
        "pricing_guardrail": (
            "Do not infer current supplier cost, selling price, margin or markup from historical evidence. "
            "Use a current supplier quote plus explicit freight, tax/clearing, financing, payment-term and internal policy inputs."
        ),
        "canonical_priority_is_unchanged": True,
        "decision_is_read_only_guidance": True,
    }
