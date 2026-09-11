from procurement_intelligence.commercial_pricing_workbench import evaluate_case


def base_case(**overrides):
    case = {
        "pricing_case_id": 1,
        "case_name": "Base",
        "pricing_currency": "KES",
        "supplier_currency": "KES",
        "supplier_cost": 700.0,
        "fx_rate_to_pricing_currency": None,
        "freight_cost": 50.0,
        "clearing_and_tax_cost": 100.0,
        "financing_cost": 25.0,
        "other_costs": 25.0,
        "selling_price": 1000.0,
        "cost_basis_complete": 1,
    }
    case.update(overrides)
    return case


def test_no_case_returns_no_case_status():
    result = evaluate_case(None)
    assert result["pricing_status"] == "NO_PRICING_CASE"
    assert result["margin_pct"] is None


def test_complete_same_currency_case_calculates_margin_and_markup():
    result = evaluate_case(base_case())
    assert result["pricing_status"] == "READY_FOR_COMMERCIAL_APPROVAL"
    assert result["total_cost"] == 900.0
    assert result["gross_profit"] == 100.0
    assert result["margin_pct"] == 10.0
    assert round(result["markup_pct"], 4) == 11.1111


def test_cross_currency_requires_explicit_fx_rate():
    result = evaluate_case(
        base_case(supplier_currency="USD", fx_rate_to_pricing_currency=None)
    )
    assert result["pricing_status"] == "MISSING_FX_RATE"
    assert result["total_cost"] is None
    assert result["margin_pct"] is None


def test_cross_currency_uses_only_explicit_fx_rate():
    result = evaluate_case(
        base_case(
            supplier_currency="USD",
            supplier_cost=5.0,
            fx_rate_to_pricing_currency=130.0,
        )
    )
    assert result["converted_supplier_cost"] == 650.0
    assert result["total_cost"] == 850.0
    assert result["gross_profit"] == 150.0
    assert result["margin_pct"] == 15.0


def test_incomplete_cost_basis_withholds_margin():
    result = evaluate_case(base_case(cost_basis_complete=0))
    assert result["pricing_status"] == "INCOMPLETE_COST_BASIS"
    assert result["total_cost"] is None
    assert result["margin_pct"] is None


def test_complete_flag_requires_explicit_zero_for_blank_components():
    result = evaluate_case(base_case(financing_cost=None))
    assert result["pricing_status"] == "MISSING_COST_COMPONENTS"
    assert result["margin_pct"] is None


def test_negative_profit_is_flagged_without_auto_decision():
    result = evaluate_case(base_case(selling_price=800.0))
    assert result["pricing_status"] == "NEGATIVE_GROSS_PROFIT"
    assert result["gross_profit"] == -100.0
    assert result["decision_is_read_only_guidance"] is True


def test_human_no_bid_takes_precedence_but_does_not_mutate_case():
    result = evaluate_case(base_case(), human_bid_decision="NO_BID")
    assert result["pricing_status"] == "HOLD_NO_BID"
    assert result["canonical_priority_is_unchanged"] is True
