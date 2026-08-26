"""Commercial intelligence enrichment helpers used by intelligence_builder.

This module intentionally contains deterministic, dependency-light rules so the
pipeline can run in CI and in local/offline environments.
"""

import re
from collections import Counter
from typing import Dict, Iterable, List, Tuple


# Approximate USD conversion factors (units of source currency per USD).
# These are deliberately conservative fallback rates for intelligence ranking,
# not accounting or treasury rates.
_FX_PER_USD = {
    "USD": 1.0,
    "US": 1.0,
    "EUR": 0.92,
    "GBP": 0.78,
    "KES": 129.0,
    "UGX": 3700.0,
    "RWF": 1400.0,
    "ETB": 145.0,
    "TZS": 2500.0,
    "SSP": 130.0,
    "SOS": 570.0,
    "CDF": 2850.0,
}


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _number(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _tokens(value: object) -> List[str]:
    text = _text(value).replace("|", ";")
    return [part.strip() for part in text.split(";") if part.strip()]


def amount_to_usd(amount: object, currency: object = "USD") -> Tuple[float, str]:
    """Return (USD amount, normalization status).

    Unknown currencies are left unconverted rather than silently applying a
    misleading rate. USD and common East African reporting currencies are
    supported using deterministic fallback rates.
    """
    number = _number(amount)
    code = _text(currency).upper().replace("$", "USD")
    code = {"US DOLLAR": "USD", "DOLLAR": "USD", "EURO": "EUR", "POUND": "GBP"}.get(code, code)

    if not number:
        return 0.0, "no_amount"

    rate = _FX_PER_USD.get(code)
    if rate is None:
        return number, f"unconverted_unknown_currency:{code or 'UNKNOWN'}"

    return round(number / rate, 2), f"converted:{code}->USD"


def canonical_donor_name(name: object) -> str:
    """Normalize common donor naming variants without aggressive fuzzy merging."""
    raw = _text(name)
    key = re.sub(r"[^a-z0-9]+", " ", raw.lower()).strip()
    key = re.sub(r"\s+", " ", key)

    aliases = {
        "world bank": "World Bank",
        "the world bank": "World Bank",
        "world bank group": "World Bank",
        "international development association": "World Bank",
        "ida": "World Bank",
        "international bank for reconstruction and development": "World Bank",
        "ib rd": "World Bank",
        "united states agency for international development": "USAID",
        "usaid": "USAID",
        "u s agency for international development": "USAID",
        "department for international development": "UK FCDO",
        "foreign commonwealth and development office": "UK FCDO",
        "foreign commonwealth development office": "UK FCDO",
        "fcdo": "UK FCDO",
        "uk foreign commonwealth development office": "UK FCDO",
        "the global fund": "The Global Fund",
        "global fund to fight aids tuberculosis and malaria": "The Global Fund",
        "global fund": "The Global Fund",
        "united nations childrens fund": "UNICEF",
        "unicef": "UNICEF",
        "world health organization": "WHO",
        "who": "WHO",
    }
    if key in aliases:
        return aliases[key]
    return raw


_EQUIPMENT_PATTERNS = [
    ("Laboratory equipment", r"\b(laboratory|lab|analy[sz]er|centrifuge|microscope|incubator|autoclave)\b"),
    ("Diagnostic equipment", r"\b(diagnostic|diagnostics|diagnosis|testing|test kits?|assay|pcr|gene ?xpert)\b"),
    ("Medical devices", r"\b(medical device|medical devices|patient monitor|infusion|ventilator|ultrasound|x[- ]?ray)\b"),
    ("Cold chain", r"\b(cold chain|refrigerator|freezer|vaccine carrier|cold storage)\b"),
    ("Blood bank equipment", r"\b(blood bank|blood storage|blood screening|apheresis|blood analyser)\b"),
    ("Health IT / information systems", r"\b(digital health|health information system|\bhis\b|\behr\b|electronic medical record|telemedicine)\b"),
    ("Facility / hospital infrastructure", r"\b(hospital|health facilit|clinic|facility|construction|renovation|rehabilitation)\b"),
    ("Vehicles / transport", r"\b(ambulance|vehicle|motorcycle|transport fleet)\b"),
]


def extract_equipment_signals(
    project_title: object,
    description: object,
    snippets: object,
    *,
    sector_codes: object = "",
    existing_categories: object = "",
) -> Dict[str, str]:
    """Extract direct and sector-inferred equipment categories."""
    title = _text(project_title)
    desc = _text(description)
    snippet = _text(snippets)
    haystack = f"{title} {desc} {snippet}".lower()

    direct: List[str] = []
    for category, pattern in _EQUIPMENT_PATTERNS:
        if re.search(pattern, haystack, flags=re.I):
            direct.append(category)

    for category in _tokens(existing_categories):
        if category and category not in direct:
            # Existing extracted categories are evidence from the source layer.
            direct.append(category)

    inferred: List[str] = []
    sectors = _text(sector_codes)
    if not direct:
        if "12220" in sectors or "12230" in sectors:
            inferred.append("Facility / hospital infrastructure")
        elif "122" in sectors:
            inferred.append("Medical devices")

    evidence = "direct_keyword" if direct else ("sector_inferred" if inferred else "")
    categories = "; ".join(dict.fromkeys(direct))
    inferred_text = "; ".join(dict.fromkeys(inferred))
    combined = categories or inferred_text

    return {
        "equipment_target_summary": combined,
        "equipment_target_snippets": snippet,
        "equipment_evidence": evidence,
        "direct_equipment_categories": categories,
        "inferred_equipment_categories": inferred_text,
    }


_MANUFACTURERS = [
    "Abbott", "Beckman Coulter", "Becton Dickinson", "BD", "Bio-Rad",
    "bioMérieux", "Cepheid", "Danaher", "Fujifilm", "GE HealthCare",
    "Hologic", "Mindray", "Nihon Kohden", "Roche", "Siemens Healthineers",
    "Sysmex", "Thermo Fisher", "Philips", "B. Braun", "Bausch + Lomb",
]


def extract_manufacturers(project_title: object, description: object, snippets: object) -> str:
    haystack = f"{_text(project_title)} {_text(description)} {_text(snippets)}"
    found = []
    lower = haystack.lower()
    for manufacturer in _MANUFACTURERS:
        if manufacturer.lower() in lower:
            found.append(manufacturer)
    return "; ".join(dict.fromkeys(found))


def herfindahl(items: Iterable[object]) -> float:
    values = [_text(item) for item in items if _text(item)]
    if not values:
        return 0.0
    counts = Counter(values)
    total = len(values)
    return round(sum((count / total) ** 2 for count in counts.values()), 3)


def donor_score(metrics: Dict[str, object]) -> Tuple[float, str]:
    """Score donor commercial attractiveness on a 0-100 deterministic scale."""
    average = max(0.0, min(100.0, _number(metrics.get("average_score"))))
    priority_share = max(0.0, min(1.0, _number(metrics.get("high_priority_share"))))
    specificity = max(0.0, min(1.0, _number(metrics.get("equipment_specificity"))))
    budget = max(0.0, _number(metrics.get("reported_budget_usd")))
    future = max(0.0, _number(metrics.get("future_disbursement_usd")))
    active = max(0.0, min(1.0, _number(metrics.get("active_share"))))
    recency = max(0.0, _number(metrics.get("recency_days")))
    countries = max(0.0, _number(metrics.get("country_count")))

    budget_component = min(15.0, (budget / 1_000_000.0) * 3.0)
    future_component = min(10.0, (future / 1_000_000.0) * 4.0)
    recency_component = 10.0 if recency <= 90 else 6.0 if recency <= 365 else 2.0 if recency < 9999 else 0.0
    country_component = min(5.0, countries)

    score = (
        average * 0.40
        + priority_share * 20.0
        + specificity * 15.0
        + active * 10.0
        + budget_component
        + future_component
        + recency_component
        + country_component
    )
    score = round(min(100.0, score), 1)

    if score >= 75:
        tier = "Tier 1"
    elif score >= 55:
        tier = "Tier 2"
    elif score >= 35:
        tier = "Tier 3"
    else:
        tier = "Monitor"
    return score, tier


def tender_model(row: Dict[str, object], as_of) -> Dict[str, object]:
    """Estimate procurement likelihood, stage and timing from available IATI signals."""
    title = _text(row.get("project_title")).lower()
    description = _text(row.get("description")).lower()
    evidence = _text(row.get("equipment_evidence"))
    direct = _tokens(row.get("direct_equipment_categories"))
    procurement = _text(row.get("procurement_signal")).lower() == "yes"
    status = _text(row.get("activity_status_code"))
    future_disb = _number(row.get("future_disbursement_usd"))
    future_budget = _number(row.get("future_budget_usd"))
    next_date = _text(row.get("next_disbursement_date")) or _text(row.get("next_budget_date"))
    score = _number(row.get("opportunity_score"))

    probability = 20.0
    reasons = []
    if direct or evidence == "direct_keyword":
        probability += 28
        reasons.append("direct equipment evidence")
    elif evidence == "sector_inferred":
        probability += 10
        reasons.append("sector-inferred equipment demand")
    if procurement:
        probability += 15
        reasons.append("procurement language")
    if future_disb > 0 or future_budget > 0:
        probability += 18
        reasons.append("future funding")
    if status == "2":
        probability += 8
        reasons.append("active programme")
    elif status == "1":
        probability += 4
        reasons.append("pipeline programme")
    if score >= 65:
        probability += 10
        reasons.append("high opportunity score")
    elif score >= 50:
        probability += 5
        reasons.append("moderate opportunity score")

    if any(term in f"{title} {description}" for term in ["tender", "procurement", "purchase", "supply", "bid"]):
        probability += 5
        reasons.append("explicit procurement wording")

    probability = round(min(100.0, probability), 1)

    if probability >= 70:
        stage = "Likely procurement"
    elif probability >= 50:
        stage = "Funding window"
    else:
        stage = "Demand signal"

    horizon = "Near term" if probability >= 70 else "Medium term" if probability >= 50 else "Longer term"
    window = next_date or "Monitor"
    confidence = "High" if len(reasons) >= 4 else "Medium" if len(reasons) >= 2 else "Low"
    basis = "; ".join(reasons) if reasons else "limited procurement evidence"
    action = (
        "Engage donor/implementer and validate procurement route now."
        if stage == "Likely procurement"
        else "Monitor funding movement and begin stakeholder mapping."
        if stage == "Funding window"
        else "Monitor programme for stronger equipment or procurement evidence."
    )

    return {
        "tender_probability": probability,
        "tender_stage": stage,
        "tender_horizon": horizon,
        "tender_window": window,
        "tender_basis": basis,
        "tender_confidence": confidence,
        "tender_evidence": "; ".join(reasons),
        "recommended_procurement_action": action,
    }
