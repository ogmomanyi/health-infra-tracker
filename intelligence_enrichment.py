#!/usr/bin/env python3

"""
Intelligence enrichment models for the health infrastructure tracker.

These functions sit on top of normalized IATI data. They do not replace
source records. They convert messy names, mixed currencies, and weak
keyword hits into commercially usable donor, equipment, and tender signals.
"""

from __future__ import annotations

import html
import math
import re
from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


USD_RATES = {
    "USD": 1.0,
    "EUR": 1.17,
    "GBP": 1.35,
    "KES": 0.00775,
    "UGX": 0.00027,
    "TZS": 0.00039,
    "RWF": 0.00069,
    "ETB": 0.00725,
    "SSP": 0.00077,
    "SOS": 0.00775,
    "CDF": 0.00035,
    "NGN": 0.00077,
    "ZAR": 0.055,
    "EGP": 0.019,
    "GHS": 0.078,
    "XOF": 0.00180,
    "XAF": 0.00180,
    "CAD": 0.73,
    "AUD": 0.65,
    "CHF": 1.25,
    "SEK": 0.108,
    "NOK": 0.095,
    "DKK": 0.157,
    "JPY": 0.0067,
    "CNY": 0.139,
    "INR": 0.0117,
}

EQUIPMENT_TAXONOMY: Dict[str, List[str]] = {
    "Diagnostic Equipment": [
        r"diagnostic",
        r"rapid test",
        r"test kit",
        r"point.of.care",
        r"in.vitro diagnostic",
        r"\bivd\b",
        r"analy[sz]er",
        r"\bgenexpert\b",
        r"\bpcr\b",
        r"molecular test",
        r"lab(oratory)? network",
    ],
    "Laboratory Systems": [
        r"laboratory equipment",
        r"lab equipment",
        r"biosafety cabinet",
        r"centrifuge",
        r"microscope",
        r"pathology",
        r"blood bank",
        r"sample transport",
        r"laboratory system",
    ],
    "Medical Devices & Equipment": [
        r"medical device",
        r"medical equipment",
        r"biomedical equipment",
        r"surgical equipment",
        r"operating theatre",
        r"operating theater",
        r"autoclave",
        r"sterili[sz]",
        r"patient monitor",
        r"defibrillator",
        r"incubator",
        r"dialysis",
        r"hospital bed",
    ],
    "Imaging": [
        r"imaging equipment",
        r"x-?ray",
        r"\bmri\b",
        r"\bct scan",
        r"ultrasound",
        r"mammograph",
        r"fluoroscop",
    ],
    "Oxygen & Respiratory": [
        r"\boxygen\b",
        r"ventilator",
        r"cpap",
        r"psa plant",
        r"oxygen plant",
        r"concentrator",
    ],
    "Cold Chain / Storage": [
        r"cold chain",
        r"cold storage",
        r"refrigerat",
        r"vaccine storage",
        r"\bfridge\b",
        r"freezer",
        r"\bilr\b",
    ],
    "Vehicles & Transport": [
        r"ambulance",
        r"\bvehicles?\b",
        r"motorcycle",
        r"\b4x4\b",
        r"fleet of",
        r"mobile clinic",
    ],
    "PPE": [
        r"personal protective equipment",
        r"\bppe\b",
        r"protective gear",
        r"protective clothing",
    ],
    "Facility Infrastructure": [
        r"construction",
        r"renovation",
        r"rehabilitat",
        r"health facilit",
        r"hospital building",
        r"clinic\b",
        r"dispensary",
        r"dispensaries",
        r"infrastructure",
        r"maternity ward",
        r"health centre",
        r"health center",
    ],
    "Power & Utilities": [
        r"solar",
        r"generator",
        r"backup power",
        r"electrification",
        r"incinerat",
        r"medical waste",
        r"water treatment",
        r"\bwash\b",
    ],
    "IT / Health Information Systems": [
        r"health information system",
        r"\bhmis\b",
        r"electronic medical record",
        r"\bemr\b",
        r"\behr\b",
        r"digital health",
        r"data system",
        r"software platform",
        r"telemedicine",
        r"telehealth",
    ],
}

SECTOR_INFERRED_EQUIPMENT = {
    "12230": "Facility Infrastructure",
    "12191": "Medical Devices & Equipment",
    "12250": "Diagnostic Equipment",
    "12262": "Diagnostic Equipment",
    "14020": "Power & Utilities",
    "14030": "Power & Utilities",
    "23030": "Power & Utilities",
    "23040": "Power & Utilities",
}

MANUFACTURER_PATTERNS: Sequence[Tuple[str, str]] = (
    ("Abbott", r"\babbott\b"),
    ("Roche", r"\broche\b"),
    ("Cepheid", r"\bcepheid\b|\bgenexpert\b"),
    ("Siemens Healthineers", r"siemens"),
    ("GE HealthCare", r"\bge healthcare\b|\bge medical\b"),
    ("Philips", r"\bphilips\b"),
    ("Mindray", r"\bmindray\b"),
    ("Bio-Rad", r"\bbio-?rad\b"),
    ("BD", r"\bbecton dickinson\b|\bbd biosciences\b"),
    ("Sysmex", r"\bsysmex\b"),
    ("Hologic", r"\bhologic\b"),
    ("Qiagen", r"\bqiagen\b"),
    ("Thermo Fisher", r"thermo fisher"),
    ("Dräger", r"\bdr[aä]ger\b"),
    ("Getinge", r"\bgetinge\b"),
    ("Stryker", r"\bstryker\b"),
    ("Medtronic", r"\bmedtronic\b"),
    ("Fujifilm", r"\bfujifilm\b"),
    ("Canon Medical", r"canon medical"),
    ("Samsung Medison", r"\bmedison\b"),
)

DONOR_FAMILY_RULES: Sequence[Tuple[str, Sequence[str]]] = (
    ("Bill & Melinda Gates Foundation", (r"gates foundation", r"bill (&|and) melinda gates", r"\bbmgf\b")),
    ("USAID", (r"\busaid\b", r"united states agency for international development")),
    ("Gavi, the Vaccine Alliance", (r"\bgavi\b",)),
    ("The Global Fund", (r"global fund", r"\bgfatm\b")),
    ("World Health Organization", (r"world health organi", r"\bwho\b")),
    ("UNICEF", (r"\bunicef\b", r"united nations children")),
    ("World Bank", (r"world bank", r"\bibrd\b", r"\bida\b", r"international development association")),
    ("FCDO / United Kingdom", (r"foreign.{0,20}development office", r"\bdfid\b", r"\bfcdo\b", r"^the united kingdom$", r"united kingdom")),
    ("European Commission", (r"european commission", r"\becho\b", r"\beuropeaid\b", r"\bdg intpa\b")),
    ("Germany / BMZ / KfW", (r"\bbmz\b", r"\bkfw\b", r"federal ministry for economic cooperation", r"giz")),
    ("France / AFD", (r"\bafd\b", r"agence fran", r"expertise france")),
    ("Japan / JICA", (r"\bjica\b", r"^japan$", r"japan international cooperation")),
    ("Canada", (r"^canada$", r"global affairs canada", r"\bcida\b")),
    ("Sweden / Sida", (r"^sweden$", r"\bsida\b", r"swedish international")),
    ("Norway / Norad", (r"^norway$", r"\bnorad\b")),
    ("Netherlands", (r"netherlands", r"\bdgid\b", r"ministry of foreign affairs of the netherlands")),
    ("Switzerland / SDC", (r"\bsdc\b", r"swiss agency for development")),
    ("Italy / AICS", (r"\baics\b", r"italian agency for cooperation")),
    ("Finland MFA", (r"ministry for foreign affairs of finland", r"finland")),
    ("UN OCHA", (r"\bunocha\b", r"ocha")),
    ("UNDP", (r"\bundp\b", r"united nations development programme")),
    ("UNFPA", (r"\bunfpa\b",)),
    ("UNOPS", (r"\bunops\b",)),
    ("African Development Bank", (r"african development bank", r"\bafdb\b")),
    ("Islamic Development Bank", (r"islamic development bank", r"\bisdb\b")),
)

_COMPILED_EQUIPMENT = {
    category: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    for category, patterns in EQUIPMENT_TAXONOMY.items()
}

_COMPILED_MANUFACTURERS = [
    (name, re.compile(pattern, re.IGNORECASE))
    for name, pattern in MANUFACTURER_PATTERNS
]

_COMPILED_DONOR_FAMILIES = [
    (family, [re.compile(pattern, re.IGNORECASE) for pattern in patterns])
    for family, patterns in DONOR_FAMILY_RULES
]


def clean_text(value: object) -> str:
    return " ".join(html.unescape(str(value or "")).split())


def split_values(value: object) -> List[str]:
    text = "" if value is None else html.unescape(str(value))
    return [
        part.strip()
        for part in text.replace("|", ";").split(";")
        if part.strip()
    ]


def normalize_org_name(value: object) -> str:
    text = clean_text(value).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(
        r"\b(the|inc|ltd|llc|org|organisation|organization|agency|foundation)\b",
        " ",
        text,
    )
    return re.sub(r"\s+", " ", text).strip()


def amount_to_usd(amount: object, currency: object) -> Tuple[float, str]:
    try:
        number = float(amount or 0)
    except (TypeError, ValueError):
        return 0.0, "NO_AMOUNT"

    if number == 0:
        return 0.0, "NO_AMOUNT"

    code = clean_text(currency).upper()

    if not code or code == "MIXED":
        return 0.0, "UNKNOWN_CURRENCY"

    rate = USD_RATES.get(code)

    if rate is None:
        return 0.0, "UNKNOWN_CURRENCY"

    return round(number * rate, 2), "CONVERTED"


def canonical_donor_name(value: object) -> str:
    original = clean_text(value)

    if not original:
        return "Unspecified donor"

    if "who foundation" in original.lower():
        return "WHO Foundation"

    normalized = normalize_org_name(original)

    if re.search(r"food for peace", normalized):
        return "USAID"

    for family, patterns in _COMPILED_DONOR_FAMILIES:
        if family == "World Health Organization" and "foundation" in normalized:
            continue

        if any(pattern.search(normalized) or pattern.search(original) for pattern in patterns):
            return family

    return original


def extract_equipment_signals(
    *texts: object,
    sector_codes: object = "",
    existing_categories: object = "",
) -> Dict[str, str]:
    haystack = " ".join(clean_text(value) for value in texts)
    categories: List[str] = []
    snippets: List[str] = []

    for category, patterns in _COMPILED_EQUIPMENT.items():
        for pattern in patterns:
            match = pattern.search(haystack)

            if not match:
                continue

            categories.append(category)
            start = max(0, match.start() - 60)
            end = min(len(haystack), match.end() + 90)
            snippets.append(f"{category}: …{haystack[start:end].strip()}…")
            break

    direct = list(dict.fromkeys(categories + split_values(existing_categories)))
    inferred = []

    for code in split_values(sector_codes):
        mapped = SECTOR_INFERRED_EQUIPMENT.get(code.strip())

        if mapped and mapped not in direct:
            inferred.append(mapped)

    inferred = list(dict.fromkeys(inferred))

    if direct:
        evidence = "direct_keyword"
        summary = "; ".join(direct)
    elif inferred:
        evidence = "sector_inferred"
        summary = "; ".join(inferred)
    else:
        evidence = "none"
        summary = ""

    return {
        "equipment_target_summary": summary,
        "equipment_target_snippets": " | ".join(dict.fromkeys(snippets)),
        "equipment_evidence": evidence,
        "direct_equipment_categories": "; ".join(direct),
        "inferred_equipment_categories": "; ".join(inferred),
    }


def extract_manufacturers(*texts: object) -> str:
    haystack = " ".join(clean_text(value) for value in texts)
    found = [
        name
        for name, pattern in _COMPILED_MANUFACTURERS
        if pattern.search(haystack)
    ]
    return "; ".join(dict.fromkeys(found))


def herfindahl(values: Iterable[str]) -> float:
    counts: Dict[str, int] = {}

    for item in values:
        text = clean_text(item)

        if not text:
            continue

        counts[text] = counts.get(text, 0) + 1

    total = sum(counts.values())

    if total <= 0:
        return 0.0

    return round(sum((count / total) ** 2 for count in counts.values()), 3)


def soonest_positive_days(deltas: Iterable[Optional[int]]) -> Optional[int]:
    upcoming = [delta for delta in deltas if delta is not None and delta >= 0]
    return min(upcoming) if upcoming else None


def tender_model(row: Dict[str, object], as_of: date) -> Dict[str, object]:
    score = 0.0
    evidence: List[str] = []
    equipment_evidence = str(row.get("equipment_evidence") or "")
    direct_categories = split_values(row.get("direct_equipment_categories"))
    procurement = str(row.get("procurement_signal") or "") == "Yes"
    status = str(row.get("activity_status_code") or "").strip()
    future_disbursement = float(row.get("future_disbursement_usd") or row.get("future_disbursement_amount") or 0)
    future_budget = float(row.get("future_budget_usd") or row.get("future_budget_amount") or 0)
    implementers = split_values(row.get("implementing_partners"))

    if equipment_evidence == "direct_keyword" or direct_categories:
        score += 26
        evidence.append("direct equipment language")
    elif equipment_evidence == "sector_inferred":
        score += 8
        evidence.append("sector-implied demand")

    if procurement:
        score += 14
        evidence.append("procurement language")

    next_dates = [
        _days_until(row.get("next_disbursement_date"), as_of),
        _days_until(row.get("next_budget_date"), as_of),
        _days_until(row.get("planned_start_date"), as_of),
    ]
    soonest = soonest_positive_days(next_dates)

    if soonest is not None:
        if soonest <= 90:
            score += 22
            evidence.append("funding window within 90 days")
        elif soonest <= 180:
            score += 16
            evidence.append("funding window within 6 months")
        elif soonest <= 365:
            score += 11
            evidence.append("funding window within 12 months")
        elif soonest <= 730:
            score += 6
            evidence.append("funding window within 24 months")

    if future_disbursement > 0:
        score += min(12, 4 + math.log10(future_disbursement + 1))
        evidence.append("future planned disbursement")

    if future_budget > 0:
        score += min(8, 2 + math.log10(future_budget + 1))
        evidence.append("future budget period")

    if status == "1":
        score += 10
        evidence.append("pipeline activity")
    elif status == "2":
        score += 7
        evidence.append("active implementation")
    elif status in {"3", "4", "5"}:
        score -= 18
        evidence.append("closed or completed activity")

    if implementers:
        score += 5
        evidence.append("named implementing buyer")

    updated_age = _days_until(row.get("last_updated"), as_of)

    if updated_age is not None:
        age = abs(updated_age) if updated_age < 0 else 0

        if age <= 180:
            score += 7
            evidence.append("updated in last 6 months")
        elif age > 730:
            score -= 8
            evidence.append("stale activity record")

    score = max(0.0, min(100.0, round(score, 1)))

    if soonest is None:
        horizon = "Unspecified"
        window = ""
        basis = str(row.get("prediction_basis") or "no dated funding signal")
    elif soonest <= 180:
        horizon = "0-6 months"
        window = str(row.get("predicted_tender_window") or "")
        basis = str(row.get("prediction_basis") or "near-term funding date")
    elif soonest <= 365:
        horizon = "6-12 months"
        window = str(row.get("predicted_tender_window") or "")
        basis = str(row.get("prediction_basis") or "12-month funding date")
    else:
        horizon = "12-24 months"
        window = str(row.get("predicted_tender_window") or "")
        basis = str(row.get("prediction_basis") or "long-range funding date")

    if window.lower() == "monitor":
        window = ""

    if score >= 70 and (direct_categories or procurement) and soonest is not None and soonest <= 365:
        stage = "Likely procurement"
    elif soonest is not None and (future_disbursement > 0 or future_budget > 0):
        stage = "Funding window"
    elif direct_categories:
        stage = "Demand signal"
    else:
        stage = "Watch"

    confidence = min(95, 30 + len(dict.fromkeys(evidence)) * 8)

    if equipment_evidence == "direct_keyword":
        action = "Map buyer, lot structure, and national/UN procurement channels before the funding window."
    elif stage == "Funding window":
        action = "Track disbursement timing and confirm whether a supply contract is expected."
    elif stage == "Demand signal":
        action = "Validate equipment need with the implementer; do not treat this as an open tender."
    else:
        action = "Keep on watch until a dated funding or procurement signal appears."

    return {
        "tender_probability": score,
        "tender_stage": stage,
        "tender_horizon": horizon,
        "tender_window": window,
        "tender_basis": basis,
        "tender_confidence": confidence,
        "tender_evidence": "; ".join(dict.fromkeys(evidence)),
        "recommended_procurement_action": action,
    }


def donor_score(metrics: Dict[str, float]) -> Tuple[float, str]:
    score = 0.0
    score += min(28, metrics.get("average_score", 0) * 0.28)
    score += min(18, metrics.get("high_priority_share", 0) * 18)
    score += min(16, metrics.get("equipment_specificity", 0) * 16)
    score += min(12, math.log10(metrics.get("reported_budget_usd", 0) + 1) * 1.4)
    score += min(10, math.log10(metrics.get("future_disbursement_usd", 0) + 1) * 1.3)
    score += min(8, metrics.get("active_share", 0) * 8)

    if metrics.get("recency_days", 9999) <= 180:
        score += 8
    elif metrics.get("recency_days", 9999) <= 365:
        score += 4

    if 2 <= metrics.get("country_count", 0) <= 8:
        score += 4

    score = max(0.0, min(100.0, round(score, 1)))

    if score >= 75 or metrics.get("high_priority_count", 0) >= 12:
        tier = "Strategic donor"
    elif score >= 55:
        tier = "Priority donor"
    elif score >= 35:
        tier = "Watch donor"
    else:
        tier = "Background"

    return score, tier


def _days_until(value: object, as_of: date) -> Optional[int]:
    text = clean_text(value)

    if not text:
        return None

    try:
        parsed = date.fromisoformat(text[:10])
    except ValueError:
        return None

    return (parsed - as_of).days
