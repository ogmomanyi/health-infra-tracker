"""Explicit commercial pricing-case calculations for opportunity execution.

All monetary calculations use user-entered current inputs. Historical evidence is
never treated as current price, and this module does not recalculate canonical
commercial priority or make a bid/no-bid decision.
"""
from __future__ import annotations

from typing import Mapping


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _upper(value: object) -> str:
    return _text(value).upper()


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid numeric value: {value}")


def _non_negative(name: str, value: float | None) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{name} cannot be negative")


def evaluate_case(
    case: Mapping[str, object] | None,
    *,
    human_bid_decision: str | None = None,
) -> dict[str, object]:
    """Evaluate one explicit pricing case without inventing missing commercial inputs."""
    if not case:
        return {
            "pricing_status": "NO_PRICING_CASE",
            "reason": "No explicit commercial pricing case has been recorded.",
            "total_cost": None,
            "gross_profit": None,
            "margin_pct": None,
            "markup_pct": None,
            "canonical_priority_is_unchanged": True,
            "decision_is_read_only_guidance": True,
        }

    pricing_currency = _upper(case.get("pricing_currency"))
    supplier_currency = _upper(case.get("supplier_currency"))
    supplier_cost = _number(case.get("supplier_cost"))
    fx_rate = _number(case.get("fx_rate_to_pricing_currency"))
    freight = _number(case.get("freight_cost"))
    clearing_tax = _number(case.get("clearing_and_tax_cost"))
    financing = _number(case.get("financing_cost"))
    other = _number(case.get("other_costs"))
    selling_price = _number(case.get("selling_price"))
    complete = str(case.get("cost_basis_complete") or "").lower() in {
        "1", "true", "yes", "y", "on"
    }

    for name, value in (
        ("supplier_cost", supplier_cost),
        ("fx_rate_to_pricing_currency", fx_rate),
        ("freight_cost", freight),
        ("clearing_and_tax_cost", clearing_tax),
        ("financing_cost", financing),
        ("other_costs", other),
        ("selling_price", selling_price),
    ):
        _non_negative(name, value)

    result = {
        "pricing_case_id": case.get("pricing_case_id"),
        "case_name": _text(case.get("case_name")) or "Pricing case",
        "pricing_currency": pricing_currency or "UNKNOWN",
        "supplier_currency": supplier_currency or "UNKNOWN",
        "supplier_cost": supplier_cost,
        "fx_rate_to_pricing_currency": fx_rate,
        "freight_cost": freight,
        "clearing_and_tax_cost": clearing_tax,
        "financing_cost": financing,
        "other_costs": other,
        "selling_price": selling_price,
        "cost_basis_complete": complete,
        "payment_terms": _text(case.get("payment_terms")),
        "quote_valid_until": _text(case.get("quote_valid_until")),
        "total_cost": None,
        "gross_profit": None,
        "margin_pct": None,
        "markup_pct": None,
        "canonical_priority_is_unchanged": True,
        "decision_is_read_only_guidance": True,
    }

    if _upper(human_bid_decision) == "NO_BID":
        result.update(
            pricing_status="HOLD_NO_BID",
            reason="The human CRM bid decision is NO_BID; pricing remains reference-only.",
        )
        return result

    if supplier_cost is None:
        result.update(
            pricing_status="MISSING_SUPPLIER_COST",
            reason="Enter the current supplier cost before evaluating commercial economics.",
        )
        return result
    if selling_price is None:
        result.update(
            pricing_status="MISSING_SELLING_PRICE",
            reason="Enter the proposed selling price before evaluating commercial economics.",
        )
        return result
    if not pricing_currency or not supplier_currency:
        result.update(
            pricing_status="MISSING_CURRENCY",
            reason="Enter both supplier and pricing currencies.",
        )
        return result

    if supplier_currency != pricing_currency:
        if fx_rate is None or fx_rate <= 0:
            result.update(
                pricing_status="MISSING_FX_RATE",
                reason=(
                    "Supplier and pricing currencies differ. Enter an explicit FX rate "
                    "expressed as pricing-currency units per supplier-currency unit."
                ),
            )
            return result
        converted_supplier_cost = supplier_cost * fx_rate
    else:
        converted_supplier_cost = supplier_cost

    result["converted_supplier_cost"] = round(converted_supplier_cost, 6)

    if not complete:
        result.update(
            pricing_status="INCOMPLETE_COST_BASIS",
            reason=(
                "Cost basis is not marked complete. Margin and markup are withheld until "
                "freight, clearing/tax, financing and other costs are explicitly confirmed."
            ),
        )
        return result

    components = {
        "freight_cost": freight,
        "clearing_and_tax_cost": clearing_tax,
        "financing_cost": financing,
        "other_costs": other,
    }
    missing = [name for name, value in components.items() if value is None]
    if missing:
        result.update(
            pricing_status="MISSING_COST_COMPONENTS",
            reason=(
                "Cost basis is marked complete but the following components are blank: "
                + ", ".join(missing)
                + ". Enter zero explicitly where no cost applies."
            ),
        )
        return result

    total_cost = converted_supplier_cost + sum(float(v) for v in components.values())
    gross_profit = selling_price - total_cost
    margin_pct = (gross_profit / selling_price * 100.0) if selling_price else None
    markup_pct = (gross_profit / total_cost * 100.0) if total_cost else None

    result.update(
        total_cost=round(total_cost, 6),
        gross_profit=round(gross_profit, 6),
        margin_pct=round(margin_pct, 4) if margin_pct is not None else None,
        markup_pct=round(markup_pct, 4) if markup_pct is not None else None,
        pricing_status="NEGATIVE_GROSS_PROFIT" if gross_profit < 0 else "READY_FOR_COMMERCIAL_APPROVAL",
        reason=(
            "Explicit current inputs produce a negative gross profit."
            if gross_profit < 0
            else "Explicit current inputs are complete and ready for human commercial approval."
        ),
    )
    return result


def evaluate_cases(
    cases: list[Mapping[str, object]],
    *,
    human_bid_decision: str | None = None,
) -> list[dict[str, object]]:
    return [
        evaluate_case(case, human_bid_decision=human_bid_decision)
        for case in cases
    ]
