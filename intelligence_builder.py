#!/usr/bin/env python3

"""
Build launch-ready intelligence and commercial layers from normalized IATI data.

The IATI fetcher creates normalized activity, transaction, budget,
disbursement, country, and organisation tables. This script follows the
project layer plan:

    RAW -> NORMALIZED -> CANONICAL -> INTELLIGENCE -> COMMERCIAL

and turns the normalized data into compact CSV/JSON products:

    data/organisation_entities.csv
    data/organisation_aliases.csv
    data/equipment_entities.csv
    data/manufacturer_entities.csv
    data/opportunity_scores.csv
    data/organisation_intelligence.csv
    data/programme_intelligence.csv
    data/donor_intelligence.csv
    data/target_accounts.csv
    data/engagements.csv
    data/crm_notes.csv
    data/recommended_actions.csv
    data/opportunities.csv
    data/equipment_intelligence.csv
    data/tender_predictions.csv
    data/market_summary.json
"""

import argparse
import hashlib
import json
import math
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

from intelligence_enrichment import (
    amount_to_usd,
    canonical_donor_name,
    donor_score,
    extract_equipment_signals,
    extract_manufacturers,
    herfindahl,
    tender_model,
)


COUNTRY_NAMES = {
    "KE": "Kenya",
    "UG": "Uganda",
    "RW": "Rwanda",
    "ET": "Ethiopia",
    "SS": "South Sudan",
    "SO": "Somalia",
    "TZ": "Tanzania",
    "CD": "Democratic Republic of the Congo",
}

PROCUREMENT_TERMS = [
    "procure",
    "procurement",
    "purchase",
    "supply",
    "supplies",
    "equipment",
    "infrastructure",
    "construction",
    "renovation",
    "rehabilitation",
    "laboratory",
    "diagnostic",
    "cold chain",
    "refrigerator",
    "ambulance",
    "digital health",
    "health information system",
]

PIPELINE_VERSION = "3.2-project-detail-intelligence"

PLAN_PROGRESS = [
    {
        "id": "01",
        "name": "Data Foundation",
        "status": "ready",
        "output": "IATI activities, budgets, transactions, countries, and organisations",
    },
    {
        "id": "02",
        "name": "Intelligence Foundation",
        "status": "ready",
        "output": "Market overview, procurement signals, opportunity identification, and scoring",
    },
    {
        "id": "03",
        "name": "Entity + Relationship Intelligence",
        "status": "ready",
        "output": "Canonical organisations, aliases, duplicate relationships, and donor intelligence",
    },
    {
        "id": "04",
        "name": "Commercial Intelligence",
        "status": "ready",
        "output": "Target accounts, engagements, CRM notes, recommended actions, and project drill-downs",
    },
    {
        "id": "05",
        "name": "Predictive / Product Intelligence",
        "status": "ready",
        "output": "Equipment/product demand intelligence, tender probability, horizon, and timing windows",
    },
]

PIPELINE_LAYERS = [
    {
        "layer": "RAW",
        "datasets": [
            "iati_activities",
            "iati_transactions",
            "iati_organisations",
        ],
        "purpose": "Preserve source-shaped IATI records before business rules.",
    },
    {
        "layer": "NORMALIZED",
        "datasets": [
            "activities",
            "transactions",
            "organisations",
        ],
        "purpose": "Store clean activity, finance, and participant records.",
    },
    {
        "layer": "CANONICAL",
        "datasets": [
            "organisation_entities",
            "organisation_aliases",
            "equipment_entities",
            "manufacturer_entities",
        ],
        "purpose": "Resolve reusable commercial entities from normalized IATI data.",
    },
    {
        "layer": "INTELLIGENCE",
        "datasets": [
            "opportunity_scores",
            "organisation_intelligence",
            "programme_intelligence",
            "donor_intelligence",
        ],
        "purpose": "Score programmes, donors, and organisations for market signals.",
    },
    {
        "layer": "COMMERCIAL",
        "datasets": [
            "target_accounts",
            "engagements",
            "crm_notes",
            "recommended_actions",
        ],
        "purpose": "Turn intelligence into sales and partnership workflows.",
    },
    {
        "layer": "PREDICTIVE_PRODUCT",
        "datasets": [
            "equipment_intelligence",
            "tender_predictions",
        ],
        "purpose": "Forecast equipment/product demand and likely procurement timing.",
    },
]

LAYER_OUTPUTS = {
    layer["layer"].lower(): layer["datasets"]
    for layer in PIPELINE_LAYERS
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build static intelligence datasets from IATI CSVs."
    )

    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory containing the normalized IATI CSV files.",
    )

    parser.add_argument(
        "--as-of",
        default=None,
        help="Analysis date in YYYY-MM-DD form. Defaults to today's UTC date.",
    )

    parser.add_argument(
        "--database",
        default="data/iati_intelligence.db",
        help="SQLite database to update with canonical, intelligence, and commercial tables.",
    )

    parser.add_argument(
        "--skip-sqlite",
        action="store_true",
        help="Write CSV/JSON artifacts only.",
    )

    return parser.parse_args()


def as_of_date(value: Optional[str]) -> date:
    if value:
        return datetime.strptime(value, "%Y-%m-%d").date()

    return datetime.now(timezone.utc).date()


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path, dtype=str, keep_default_na=False)


def read_first_available_csv(data_dir: Path, *names: str) -> pd.DataFrame:
    for name in names:
        dataframe = read_csv(data_dir / name)

        if not dataframe.empty:
            return dataframe

    return pd.DataFrame()


def clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def stable_id(prefix: str, *parts: object) -> str:
    payload = "|".join(
        clean_text(part).lower()
        for part in parts
        if clean_text(part)
    )

    if not payload:
        payload = "unknown"

    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]

    return f"{prefix}_{digest}"


def organisation_entity_key(org_ref: object, org_name: object) -> str:
    ref = clean_text(org_ref)

    if ref:
        return f"ref:{ref.lower()}"

    return f"name:{clean_text(org_name).lower()}"


def split_values(value: object) -> List[str]:
    text = "" if value is None else str(value)

    return [
        part.strip()
        for part in text.replace("|", ";").split(";")
        if part.strip()
    ]


def safe_float(value: object) -> float:
    try:
        if value is None or value == "":
            return 0.0

        number = float(value)

        if math.isnan(number) or math.isinf(number):
            return 0.0

        return number
    except (TypeError, ValueError):
        return 0.0


def numeric_values(dataframe: pd.DataFrame, column: str) -> List[float]:
    if dataframe.empty or column not in dataframe.columns:
        return []

    values = dataframe.loc[:, column]

    if isinstance(values, pd.DataFrame):
        values = values.iloc[:, 0]

    return [safe_float(value) for value in values.tolist()]


def sum_numeric(dataframe: pd.DataFrame, column: str) -> float:
    return float(sum(numeric_values(dataframe, column)))


def mean_numeric(dataframe: pd.DataFrame, column: str) -> float:
    values = numeric_values(dataframe, column)

    if not values:
        return 0.0

    return float(sum(values) / len(values))


def count_column_value(dataframe: pd.DataFrame, column: str, value: str) -> int:
    if dataframe.empty or column not in dataframe.columns:
        return 0

    return int((dataframe[column] == value).sum())


def safe_date(value: object) -> Optional[date]:
    text = "" if value is None else str(value).strip()

    if not text:
        return None

    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None


def quarter_label(value: Optional[date]) -> str:
    if value is None:
        return ""

    quarter = ((value.month - 1) // 3) + 1

    return f"Q{quarter} {value.year}"


def days_until(value: Optional[date], as_of: date) -> Optional[int]:
    if value is None:
        return None

    return (value - as_of).days


def first_future_date(values: Iterable[object], as_of: date) -> Optional[date]:
    dates = [
        parsed
        for parsed in (safe_date(value) for value in values)
        if parsed is not None and parsed >= as_of
    ]

    if not dates:
        return None

    return min(dates)


def text_contains_procurement_signal(*values: object) -> bool:
    haystack = " ".join(str(value or "") for value in values).lower()

    return any(term in haystack for term in PROCUREMENT_TERMS)


def format_top(items: Iterable[str], limit: int = 4) -> str:
    counts: Dict[str, int] = {}

    for item in items:
        item = clean_text(item)

        if not item:
            continue

        counts[item] = counts.get(item, 0) + 1

    ranked = sorted(
        counts.items(),
        key=lambda entry: (-entry[1], entry[0]),
    )

    return "; ".join(item for item, _ in ranked[:limit])


def top_value(items: Iterable[object], default: str = "") -> str:
    value = format_top(
        (clean_text(item) for item in items),
        limit=1,
    )

    return value or default


def country_names_from_codes(value: object) -> str:
    return "; ".join(
        COUNTRY_NAMES.get(code, code)
        for code in split_values(value)
    )


def join_unique(values: Iterable[object]) -> str:
    seen = {}

    for value in values:
        text = clean_text(value)

        if text:
            seen[text] = True

    return "; ".join(seen.keys())


def classify_account_type(roles_value: object) -> str:
    roles = set(split_values(roles_value))

    if "funding" in roles:
        return "Donor"

    if "implementing" in roles:
        return "Implementing Partner"

    if "accountable" in roles:
        return "Accountable Agency"

    if "reporting" in roles:
        return "Reporting Organisation"

    return "Organisation"


def priority_tier(score: float, high_priority_count: int) -> str:
    if score >= 75 or high_priority_count >= 3:
        return "Tier 1"

    if score >= 55 or high_priority_count >= 1:
        return "Tier 2"

    if score >= 35:
        return "Tier 3"

    return "Monitor"


def sum_by_activity(
    dataframe: pd.DataFrame,
    amount_col: str = "amount",
) -> pd.DataFrame:
    if dataframe.empty or "activity_id" not in dataframe.columns:
        return pd.DataFrame(columns=["activity_id", amount_col])

    work = dataframe.copy()
    work[amount_col] = work[amount_col].apply(safe_float)

    return (
        work.groupby("activity_id", as_index=False)[amount_col]
        .sum()
    )


def build_transaction_summary(transactions: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "activity_id",
        "commitment_amount",
        "disbursement_amount",
        "expenditure_amount",
        "latest_transaction_date",
    ]

    if transactions.empty:
        return pd.DataFrame(columns=columns)

    work = transactions.copy()
    work["amount"] = work["amount"].apply(safe_float)

    frames = []

    for code, column in [
        ("2", "commitment_amount"),
        ("3", "disbursement_amount"),
        ("4", "expenditure_amount"),
    ]:
        filtered = work[work.get("transaction_type_code", "") == code]
        summary = (
            filtered.groupby("activity_id", as_index=False)["amount"].sum()
            if not filtered.empty
            else pd.DataFrame(columns=["activity_id", "amount"])
        )
        summary = summary.rename(columns={"amount": column})
        frames.append(summary)

    latest = (
        work.groupby("activity_id", as_index=False)["transaction_date"]
        .max()
        .rename(columns={"transaction_date": "latest_transaction_date"})
    )

    output = latest

    for frame in frames:
        output = output.merge(frame, on="activity_id", how="left")

    for column in columns:
        if column not in output.columns:
            output[column] = 0.0 if column.endswith("_amount") else ""

    return output[columns].fillna(0)


def build_future_summary(
    dataframe: pd.DataFrame,
    as_of: date,
    prefix: str,
) -> pd.DataFrame:
    columns = [
        "activity_id",
        f"future_{prefix}_amount",
        f"next_{prefix}_date",
        f"next_{prefix}_quarter",
    ]

    if dataframe.empty:
        return pd.DataFrame(columns=columns)

    work = dataframe.copy()
    work["amount"] = work["amount"].apply(safe_float)
    work["period_start_date"] = work["period_start"].apply(safe_date)
    work["period_end_date"] = work["period_end"].apply(safe_date)

    future = work[
        (work["period_start_date"].notna() & (work["period_start_date"] >= as_of))
        | (work["period_end_date"].notna() & (work["period_end_date"] >= as_of))
    ].copy()

    if future.empty:
        return pd.DataFrame(columns=columns)

    rows = []

    for activity_id, group in future.groupby("activity_id"):
        next_date = first_future_date(group["period_start"], as_of)

        if next_date is None:
            next_date = first_future_date(group["period_end"], as_of)

        rows.append({
            "activity_id": activity_id,
            f"future_{prefix}_amount": group["amount"].sum(),
            f"next_{prefix}_date": next_date.isoformat() if next_date else "",
            f"next_{prefix}_quarter": quarter_label(next_date),
        })

    return pd.DataFrame(rows, columns=columns)


def score_opportunity(row: pd.Series, as_of: date) -> Dict[str, object]:
    score = 0.0
    signals = []

    equipment = split_values(row.get("direct_equipment_categories") or row.get("equipment_target_summary"))
    evidence = str(row.get("equipment_evidence", "")).strip()
    budget = safe_float(row.get("budget_usd")) or safe_float(row.get("total_budget_amount"))
    future_disbursement = (
        safe_float(row.get("future_disbursement_usd"))
        or safe_float(row.get("future_disbursement_amount"))
    )
    future_budget = (
        safe_float(row.get("future_budget_usd"))
        or safe_float(row.get("future_budget_amount"))
    )
    status_code = str(row.get("activity_status_code", "")).strip()

    if evidence == "direct_keyword" or equipment:
        score += 28
        signals.append("equipment demand")
    elif evidence == "sector_inferred":
        score += 10
        signals.append("sector-implied equipment demand")
    elif "12230" in str(row.get("sector_codes", "")):
        score += 10
        signals.append("health infrastructure sector")

    if status_code == "1":
        score += 18
        signals.append("pipeline stage")
    elif status_code == "2":
        score += 12
        signals.append("active implementation")

    if future_disbursement > 0:
        score += min(20, 8 + math.log10(future_disbursement + 1) * 2)
        signals.append("future planned disbursement")

    if future_budget > 0:
        score += min(12, 4 + math.log10(future_budget + 1))
        signals.append("future budget cycle")

    if budget > 0:
        score += min(12, math.log10(budget + 1) * 1.5)
        signals.append("reported budget")

    next_dates = [
        safe_date(row.get("next_disbursement_date")),
        safe_date(row.get("next_budget_date")),
        safe_date(row.get("planned_start_date")),
    ]

    upcoming = [
        delta
        for delta in (days_until(value, as_of) for value in next_dates)
        if delta is not None and delta >= 0
    ]

    if upcoming:
        soonest = min(upcoming)

        if soonest <= 180:
            score += 10
            signals.append("near-term funding window")
        elif soonest <= 365:
            score += 7
            signals.append("12-month funding window")
        elif soonest <= 730:
            score += 4
            signals.append("long-range funding window")

    updated = safe_date(row.get("last_updated"))

    if updated:
        age = (as_of - updated).days

        if age <= 90:
            score += 8
            signals.append("recently updated")
        elif age <= 365:
            score += 4
            signals.append("updated within 12 months")

    if text_contains_procurement_signal(
        row.get("project_title"),
        row.get("description"),
        row.get("equipment_target_snippets"),
    ):
        score += 8
        signals.append("procurement language")

    score = max(0, min(100, round(score, 1)))

    if score >= 75:
        priority = "Strategic Priority"
    elif score >= 60:
        priority = "Qualified Lead"
    elif score >= 40:
        priority = "Watchlist"
    else:
        priority = "Long Range"

    confidence = min(95, 35 + len(set(signals)) * 9)

    return {
        "opportunity_score": score,
        "priority_band": priority,
        "confidence": confidence,
        "signal_summary": "; ".join(dict.fromkeys(signals)),
    }


def predicted_window(row: pd.Series, as_of: date) -> Dict[str, str]:
    next_disbursement = safe_date(row.get("next_disbursement_date"))
    next_budget = safe_date(row.get("next_budget_date"))
    planned_start = safe_date(row.get("planned_start_date"))
    planned_end = safe_date(row.get("planned_end_date"))

    if next_disbursement:
        return {
            "predicted_tender_window": quarter_label(next_disbursement),
            "prediction_basis": "next planned disbursement",
        }

    if next_budget:
        return {
            "predicted_tender_window": quarter_label(next_budget),
            "prediction_basis": "next budget period",
        }

    if planned_start and planned_start >= as_of:
        return {
            "predicted_tender_window": quarter_label(planned_start),
            "prediction_basis": "planned activity start",
        }

    if planned_end and planned_end >= as_of:
        return {
            "predicted_tender_window": f"Active through {quarter_label(planned_end)}",
            "prediction_basis": "active implementation period",
        }

    return {
        "predicted_tender_window": "Monitor",
        "prediction_basis": "no future dated funding signal",
    }


def recommended_action(row: pd.Series) -> str:
    stage = str(row.get("tender_stage", ""))
    procurement_action = clean_text(row.get("recommended_procurement_action"))

    if stage == "Likely procurement" and procurement_action:
        return procurement_action

    score = safe_float(row.get("opportunity_score"))
    basis = str(row.get("prediction_basis", ""))

    if score >= 75:
        return "Qualify donor route, map implementers, and monitor national procurement portals."

    if "planned disbursement" in basis or "budget" in basis:
        return "Track funding release timing and prepare category-specific supplier positioning."

    if split_values(row.get("equipment_target_summary")):
        return "Validate procurement owner and shortlist likely equipment lots."

    return "Keep on watchlist and revisit when the activity is updated."


def build_opportunities(
    activities: pd.DataFrame,
    transactions: pd.DataFrame,
    budgets: pd.DataFrame,
    planned: pd.DataFrame,
    as_of: date,
) -> pd.DataFrame:
    if activities.empty:
        return pd.DataFrame()

    base = activities.copy()

    base = base.merge(
        build_transaction_summary(transactions),
        left_on="iati_identifier",
        right_on="activity_id",
        how="left",
    )

    base = base.merge(
        build_future_summary(planned, as_of, "disbursement"),
        left_on="iati_identifier",
        right_on="activity_id",
        how="left",
        suffixes=("", "_planned"),
    )

    base = base.merge(
        build_future_summary(budgets, as_of, "budget"),
        left_on="iati_identifier",
        right_on="activity_id",
        how="left",
        suffixes=("", "_budget"),
    )

    for column in [
        "commitment_amount",
        "disbursement_amount",
        "expenditure_amount",
        "future_disbursement_amount",
        "future_budget_amount",
    ]:
        if column not in base.columns:
            base[column] = 0.0

        base[column] = base[column].apply(safe_float)

    equipment_rows = base.apply(
        lambda row: pd.Series(
            extract_equipment_signals(
                row.get("project_title"),
                row.get("description"),
                row.get("equipment_target_snippets"),
                sector_codes=row.get("sector_codes"),
                existing_categories=row.get("equipment_target_summary"),
            )
        ),
        axis=1,
    )
    base = pd.concat(
        [base.drop(columns=["equipment_target_summary", "equipment_target_snippets"], errors="ignore"), equipment_rows],
        axis=1,
    )
    base["manufacturer_mentions"] = base.apply(
        lambda row: extract_manufacturers(
            row.get("project_title"),
            row.get("description"),
            row.get("equipment_target_snippets"),
        ),
        axis=1,
    )
    usd_budget = base.apply(
        lambda row: pd.Series(
            dict(zip(
                ["budget_usd", "budget_normalization_status"],
                amount_to_usd(row.get("total_budget_amount"), row.get("budget_currency") or row.get("default_currency")),
            ))
        ),
        axis=1,
    )
    usd_future_disb = base.apply(
        lambda row: pd.Series(
            dict(zip(
                ["future_disbursement_usd", "_future_disb_fx"],
                amount_to_usd(row.get("future_disbursement_amount"), row.get("default_currency")),
            ))
        ),
        axis=1,
    )
    usd_future_budget = base.apply(
        lambda row: pd.Series(
            dict(zip(
                ["future_budget_usd", "_future_budget_fx"],
                amount_to_usd(row.get("future_budget_amount"), row.get("budget_currency") or row.get("default_currency")),
            ))
        ),
        axis=1,
    )
    usd_disbursed = base.apply(
        lambda row: pd.Series(
            dict(zip(
                ["disbursement_usd", "_disb_fx"],
                amount_to_usd(row.get("disbursement_amount"), row.get("default_currency")),
            ))
        ),
        axis=1,
    )
    base = pd.concat([base, usd_budget, usd_future_disb, usd_future_budget, usd_disbursed], axis=1)

    score_rows = base.apply(
        lambda row: pd.Series(score_opportunity(row, as_of)),
        axis=1,
    )

    window_rows = base.apply(
        lambda row: pd.Series(predicted_window(row, as_of)),
        axis=1,
    )

    output = pd.concat([base, score_rows, window_rows], axis=1)
    output["procurement_signal"] = output.apply(
        lambda row: "Yes"
        if split_values(row.get("direct_equipment_categories"))
        or text_contains_procurement_signal(
            row.get("project_title"),
            row.get("description"),
            row.get("equipment_target_snippets"),
        )
        else "No",
        axis=1,
    )
    tender_rows = output.apply(
        lambda row: pd.Series(tender_model(row.to_dict(), as_of)),
        axis=1,
    )
    output = pd.concat([output, tender_rows], axis=1)
    output["recommended_action"] = output.apply(recommended_action, axis=1)

    output["country_names"] = output["country_codes"].apply(
        lambda value: "; ".join(
            COUNTRY_NAMES.get(code, code)
            for code in split_values(value)
        )
    )

    selected_columns = [
        "iati_identifier",
        "project_title",
        "reporting_org_name",
        "funding_agencies",
        "implementing_partners",
        "accountable_orgs",
        "country_codes",
        "country_names",
        "activity_status_code",
        "activity_status_label",
        "planned_start_date",
        "planned_end_date",
        "last_updated",
        "default_currency",
        "total_budget_amount",
        "budget_currency",
        "budget_usd",
        "budget_normalization_status",
        "commitment_amount",
        "disbursement_amount",
        "disbursement_usd",
        "expenditure_amount",
        "future_disbursement_amount",
        "future_disbursement_usd",
        "future_budget_amount",
        "future_budget_usd",
        "next_disbursement_date",
        "next_disbursement_quarter",
        "next_budget_date",
        "next_budget_quarter",
        "sector_codes",
        "sector_names",
        "equipment_target_summary",
        "equipment_target_snippets",
        "equipment_evidence",
        "direct_equipment_categories",
        "inferred_equipment_categories",
        "manufacturer_mentions",
        "procurement_signal",
        "opportunity_score",
        "priority_band",
        "confidence",
        "signal_summary",
        "predicted_tender_window",
        "prediction_basis",
        "tender_probability",
        "tender_stage",
        "tender_horizon",
        "tender_window",
        "tender_basis",
        "tender_confidence",
        "tender_evidence",
        "recommended_procurement_action",
        "recommended_action",
        "description",
    ]

    for column in selected_columns:
        if column not in output.columns:
            output[column] = ""

    return (
        output[selected_columns]
        .sort_values(
            by=["opportunity_score", "confidence", "total_budget_amount"],
            ascending=[False, False, False],
        )
        .reset_index(drop=True)
    )


def build_donor_intelligence(opportunities: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "donor_intelligence_id",
        "donor_name",
        "source_aliases",
        "project_count",
        "active_projects",
        "pipeline_projects",
        "reported_budget",
        "reported_budget_usd",
        "disbursement_usd",
        "future_disbursement_usd",
        "disbursement_ratio",
        "average_score",
        "high_priority_opportunities",
        "likely_procurement_count",
        "top_countries",
        "country_count",
        "country_concentration",
        "top_implementers",
        "top_equipment_categories",
        "equipment_specificity",
        "next_window",
        "latest_update",
        "donor_score",
        "commercial_priority",
        "intelligence_notes",
        "source_layer",
    ]

    if opportunities.empty:
        return pd.DataFrame(columns=columns)

    rows = []

    for _, row in opportunities.iterrows():
        donors = split_values(row.get("funding_agencies"))

        if not donors:
            donors = [row.get("reporting_org_name", "Unspecified") or "Unspecified"]

        for donor in donors:
            rows.append({
                "source_name": donor,
                "donor_name": canonical_donor_name(donor),
                "iati_identifier": row.get("iati_identifier"),
                "country_codes": row.get("country_codes"),
                "implementing_partners": row.get("implementing_partners"),
                "equipment_target_summary": row.get("direct_equipment_categories") or row.get("equipment_target_summary"),
                "equipment_evidence": row.get("equipment_evidence"),
                "activity_status_code": row.get("activity_status_code"),
                "total_budget_amount": safe_float(row.get("total_budget_amount")),
                "budget_usd": safe_float(row.get("budget_usd")),
                "disbursement_usd": safe_float(row.get("disbursement_usd")),
                "future_disbursement_usd": safe_float(row.get("future_disbursement_usd")),
                "opportunity_score": safe_float(row.get("opportunity_score")),
                "priority_band": row.get("priority_band"),
                "tender_stage": row.get("tender_stage"),
                "tender_window": row.get("tender_window") or row.get("predicted_tender_window"),
                "last_updated": row.get("last_updated"),
            })

    exploded = pd.DataFrame(rows)
    output = []

    for donor, group in exploded.groupby("donor_name"):
        countries = [
            country
            for value in group["country_codes"]
            for country in split_values(value)
        ]
        equipment = [
            category
            for value in group["equipment_target_summary"]
            for category in split_values(value)
        ]
        implementers = [
            partner
            for value in group["implementing_partners"]
            for partner in split_values(value)
        ]
        project_count = int(group["iati_identifier"].nunique())
        high_priority = int(
            group["priority_band"].isin([
                "Strategic Priority",
                "Qualified Lead",
            ]).sum()
        )
        direct_equipment = int((group["equipment_evidence"] == "direct_keyword").sum())
        budget_usd = round(group["budget_usd"].sum(), 2)
        disbursed = round(group["disbursement_usd"].sum(), 2)
        future_disb = round(group["future_disbursement_usd"].sum(), 2)
        latest_update = group["last_updated"].max()
        recency_days = 9999
        latest_date = safe_date(latest_update)

        if latest_date:
            recency_days = abs((date.today() - latest_date).days)

        dated_windows = [
            window
            for window in group["tender_window"].tolist()
            if clean_text(window) and clean_text(window).lower() != "monitor"
        ]
        score, tier = donor_score({
            "average_score": float(group["opportunity_score"].mean()),
            "high_priority_share": high_priority / project_count if project_count else 0,
            "high_priority_count": high_priority,
            "equipment_specificity": direct_equipment / project_count if project_count else 0,
            "reported_budget_usd": budget_usd,
            "future_disbursement_usd": future_disb,
            "active_share": float((group["activity_status_code"] == "2").mean()),
            "recency_days": recency_days,
            "country_count": len(set(countries)),
        })
        notes = []

        if direct_equipment / project_count >= 0.25 if project_count else False:
            notes.append("High equipment specificity")

        if future_disb > 0:
            notes.append("Has dated future disbursements")

        if int((group["tender_stage"] == "Likely procurement").sum()) > 0:
            notes.append("Contains likely procurement programmes")

        output.append({
            "donor_name": donor,
            "source_aliases": join_unique(group["source_name"]),
            "project_count": project_count,
            "active_projects": int((group["activity_status_code"] == "2").sum()),
            "pipeline_projects": int((group["activity_status_code"] == "1").sum()),
            "reported_budget": round(group["total_budget_amount"].sum(), 2),
            "reported_budget_usd": budget_usd,
            "disbursement_usd": disbursed,
            "future_disbursement_usd": future_disb,
            "disbursement_ratio": round(disbursed / budget_usd, 3) if budget_usd else 0,
            "average_score": round(group["opportunity_score"].mean(), 1),
            "high_priority_opportunities": high_priority,
            "likely_procurement_count": int((group["tender_stage"] == "Likely procurement").sum()),
            "top_countries": format_top(countries),
            "country_count": len(set(countries)),
            "country_concentration": herfindahl(countries),
            "top_implementers": format_top(implementers),
            "top_equipment_categories": format_top(equipment),
            "equipment_specificity": round(direct_equipment / project_count, 3) if project_count else 0,
            "next_window": format_top(dated_windows, limit=2) or "No dated window",
            "latest_update": latest_update,
            "donor_score": score,
            "commercial_priority": tier,
            "intelligence_notes": "; ".join(notes) or "Baseline donor profile",
        })

    dataframe = pd.DataFrame(output)
    dataframe["donor_intelligence_id"] = dataframe["donor_name"].apply(
        lambda value: stable_id("donor_intel", value)
    )
    dataframe["source_layer"] = "intelligence"

    return (
        dataframe[columns]
        .sort_values(
            by=["donor_score", "high_priority_opportunities", "reported_budget_usd"],
            ascending=[False, False, False],
        )
        .reset_index(drop=True)
    )


def build_equipment_intelligence(opportunities: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "equipment_category",
        "evidence_quality",
        "project_count",
        "direct_evidence_projects",
        "inferred_projects",
        "active_projects",
        "pipeline_projects",
        "reported_budget",
        "reported_budget_usd",
        "future_disbursement_usd",
        "average_score",
        "high_priority_opportunities",
        "likely_procurement_count",
        "top_countries",
        "top_donors",
        "next_windows",
        "demand_intensity",
    ]

    if opportunities.empty:
        return pd.DataFrame(columns=columns)

    rows = []

    for _, row in opportunities.iterrows():
        direct = split_values(row.get("direct_equipment_categories"))
        inferred = [
            category
            for category in split_values(row.get("inferred_equipment_categories"))
            if category not in direct
        ]

        for category in direct:
            rows.append(_equipment_row(row, category, "direct_keyword"))

        for category in inferred:
            rows.append(_equipment_row(row, category, "sector_inferred"))

    if not rows:
        return pd.DataFrame(columns=columns)

    exploded = pd.DataFrame(rows)
    output = []

    for category, group in exploded.groupby("equipment_category"):
        countries = [
            country
            for value in group["country_codes"]
            for country in split_values(value)
        ]
        donors = [
            canonical_donor_name(donor)
            for value in group["funding_agencies"]
            for donor in split_values(value)
        ]
        project_count = int(group["iati_identifier"].nunique())
        direct_count = int((group["evidence_quality"] == "direct_keyword").sum())
        high_priority = int(
            group["priority_band"].isin([
                "Strategic Priority",
                "Qualified Lead",
            ]).sum()
        )
        likely = int((group["tender_stage"] == "Likely procurement").sum())
        intensity = round(
            min(100, (direct_count * 2 + likely * 3 + high_priority) / max(project_count, 1) * 20),
            1,
        )
        dated_windows = [
            window
            for window in group["tender_window"].tolist()
            if clean_text(window) and clean_text(window).lower() != "monitor"
        ]

        output.append({
            "equipment_category": category,
            "evidence_quality": (
                "direct_keyword"
                if direct_count
                else "sector_inferred"
            ),
            "project_count": project_count,
            "direct_evidence_projects": direct_count,
            "inferred_projects": int((group["evidence_quality"] == "sector_inferred").sum()),
            "active_projects": int((group["activity_status_code"] == "2").sum()),
            "pipeline_projects": int((group["activity_status_code"] == "1").sum()),
            "reported_budget": round(group["total_budget_amount"].sum(), 2),
            "reported_budget_usd": round(group["budget_usd"].sum(), 2),
            "future_disbursement_usd": round(group["future_disbursement_usd"].sum(), 2),
            "average_score": round(group["opportunity_score"].mean(), 1),
            "high_priority_opportunities": high_priority,
            "likely_procurement_count": likely,
            "top_countries": format_top(countries),
            "top_donors": format_top(donors),
            "next_windows": format_top(dated_windows, limit=3) or "No dated window",
            "demand_intensity": intensity,
        })

    return (
        pd.DataFrame(output, columns=columns)
        .sort_values(
            by=["demand_intensity", "likely_procurement_count", "reported_budget_usd"],
            ascending=[False, False, False],
        )
        .reset_index(drop=True)
    )


def _equipment_row(row: pd.Series, category: str, evidence: str) -> Dict[str, object]:
    return {
        "equipment_category": category,
        "evidence_quality": evidence,
        "iati_identifier": row.get("iati_identifier"),
        "country_codes": row.get("country_codes"),
        "funding_agencies": row.get("funding_agencies"),
        "activity_status_code": row.get("activity_status_code"),
        "total_budget_amount": safe_float(row.get("total_budget_amount")),
        "budget_usd": safe_float(row.get("budget_usd")),
        "future_disbursement_usd": safe_float(row.get("future_disbursement_usd")),
        "opportunity_score": safe_float(row.get("opportunity_score")),
        "priority_band": row.get("priority_band"),
        "tender_stage": row.get("tender_stage"),
        "tender_window": row.get("tender_window") or row.get("predicted_tender_window"),
    }


def build_tender_predictions(opportunities: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "iati_identifier",
        "project_title",
        "country_codes",
        "country_names",
        "funding_agencies",
        "implementing_partners",
        "equipment_target_summary",
        "equipment_evidence",
        "tender_probability",
        "tender_stage",
        "tender_horizon",
        "tender_window",
        "tender_basis",
        "tender_confidence",
        "tender_evidence",
        "opportunity_score",
        "priority_band",
        "future_disbursement_usd",
        "future_budget_usd",
        "recommended_action",
    ]

    if opportunities.empty:
        return pd.DataFrame(columns=columns)

    work = opportunities.copy()
    work["tender_probability"] = work["tender_probability"].apply(safe_float)
    closed = work["activity_status_code"].isin(["3", "4", "5"])
    dated = work["tender_window"].fillna("").astype(str).str.strip().ne("")
    direct = work["equipment_evidence"].eq("direct_keyword")
    procurement = work["procurement_signal"].eq("Yes")

    filtered = work[
        (work["tender_probability"] >= 45)
        & (~closed | dated)
        & (direct | procurement | dated)
        & work["tender_stage"].isin(["Likely procurement", "Funding window", "Demand signal"])
    ].copy()
    filtered["recommended_action"] = filtered.get(
        "recommended_procurement_action",
        filtered.get("recommended_action"),
    )

    for column in columns:
        if column not in filtered.columns:
            filtered[column] = ""

    return (
        filtered[columns]
        .sort_values(
            by=["tender_probability", "tender_confidence", "opportunity_score"],
            ascending=[False, False, False],
        )
        .reset_index(drop=True)
    )


def build_organisation_entities(
    organisations: pd.DataFrame,
    opportunities: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "organisation_entity_id",
        "canonical_name",
        "primary_org_ref",
        "org_refs",
        "org_types",
        "roles",
        "activity_count",
        "active_activity_count",
        "pipeline_activity_count",
        "country_codes",
        "country_names",
        "reported_budget",
        "average_opportunity_score",
        "high_priority_opportunities",
        "top_equipment_categories",
        "latest_update",
        "source_layer",
    ]

    if organisations.empty:
        return pd.DataFrame(columns=columns)

    work = organisations.copy()

    for column in ["activity_id", "org_ref", "org_name", "role", "org_type"]:
        if column not in work.columns:
            work[column] = ""

    work["org_ref"] = work["org_ref"].apply(clean_text)
    work["org_name"] = work["org_name"].apply(clean_text)
    work["entity_key"] = work.apply(
        lambda row: organisation_entity_key(
            row.get("org_ref"),
            row.get("org_name"),
        ),
        axis=1,
    )
    work = work[
        (work["org_ref"] != "")
        | (work["org_name"] != "")
    ].copy()

    if work.empty:
        return pd.DataFrame(columns=columns)

    if opportunities.empty or "iati_identifier" not in opportunities.columns:
        opportunity_work = pd.DataFrame(columns=["iati_identifier"])
    else:
        opportunity_work = opportunities.copy()

    rows = []

    for entity_key, group in work.groupby("entity_key"):
        activity_ids = list(dict.fromkeys(
            clean_text(value)
            for value in group["activity_id"]
            if clean_text(value)
        ))

        related = opportunity_work[
            opportunity_work.get("iati_identifier", "").isin(activity_ids)
        ].copy()

        countries = [
            country
            for value in related.get("country_codes", [])
            for country in split_values(value)
        ]
        equipment = [
            category
            for value in related.get("equipment_target_summary", [])
            for category in split_values(value)
        ]

        primary_ref = top_value(group["org_ref"])
        canonical_name = top_value(
            group["org_name"],
            default=primary_ref or "Unspecified organisation",
        )
        average_score = mean_numeric(related, "opportunity_score")

        rows.append({
            "organisation_entity_id": stable_id("org", entity_key),
            "canonical_name": canonical_name,
            "primary_org_ref": primary_ref,
            "org_refs": join_unique(group["org_ref"]),
            "org_types": join_unique(group["org_type"]),
            "roles": join_unique(group["role"]),
            "activity_count": int(len(set(activity_ids))),
            "active_activity_count": count_column_value(
                related,
                "activity_status_code",
                "2",
            ),
            "pipeline_activity_count": count_column_value(
                related,
                "activity_status_code",
                "1",
            ),
            "country_codes": join_unique(countries),
            "country_names": country_names_from_codes(join_unique(countries)),
            "reported_budget": round(sum_numeric(related, "total_budget_amount"), 2),
            "average_opportunity_score": round(average_score, 1),
            "high_priority_opportunities": int(
                related.get("priority_band", pd.Series(dtype=str))
                .isin([
                    "Strategic Priority",
                    "Qualified Lead",
                ])
                .sum()
            ),
            "top_equipment_categories": format_top(equipment),
            "latest_update": (
                related.get("last_updated", pd.Series(dtype=str)).max()
                if not related.empty
                else ""
            ),
            "source_layer": "canonical",
        })

    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values(
            by=["high_priority_opportunities", "reported_budget", "activity_count"],
            ascending=[False, False, False],
        )
        .reset_index(drop=True)
    )


def build_organisation_aliases(organisations: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "organisation_alias_id",
        "organisation_entity_id",
        "alias",
        "org_ref",
        "role",
        "source_activity_count",
        "source_layer",
    ]

    if organisations.empty:
        return pd.DataFrame(columns=columns)

    work = organisations.copy()

    for column in ["activity_id", "org_ref", "org_name", "role"]:
        if column not in work.columns:
            work[column] = ""

    work["org_ref"] = work["org_ref"].apply(clean_text)
    work["alias"] = work["org_name"].apply(clean_text)
    work = work[
        (work["org_ref"] != "")
        | (work["alias"] != "")
    ].copy()

    if work.empty:
        return pd.DataFrame(columns=columns)

    work["organisation_entity_id"] = work.apply(
        lambda row: stable_id(
            "org",
            organisation_entity_key(row.get("org_ref"), row.get("alias")),
        ),
        axis=1,
    )

    rows = []

    for key, group in work.groupby([
        "organisation_entity_id",
        "alias",
        "org_ref",
        "role",
    ]):
        entity_id, alias, org_ref, role = key

        rows.append({
            "organisation_alias_id": stable_id(
                "org_alias",
                entity_id,
                alias,
                org_ref,
                role,
            ),
            "organisation_entity_id": entity_id,
            "alias": alias or org_ref,
            "org_ref": org_ref,
            "role": role,
            "source_activity_count": int(group["activity_id"].nunique()),
            "source_layer": "canonical",
        })

    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values(
            by=["source_activity_count", "alias"],
            ascending=[False, True],
        )
        .reset_index(drop=True)
    )


def build_equipment_entities(opportunities: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "equipment_entity_id",
        "equipment_category",
        "activity_count",
        "active_activity_count",
        "pipeline_activity_count",
        "reported_budget",
        "average_opportunity_score",
        "high_priority_opportunities",
        "country_codes",
        "country_names",
        "top_donors",
        "next_windows",
        "source_layer",
    ]

    if opportunities.empty:
        return pd.DataFrame(columns=columns)

    rows = []

    for _, row in opportunities.iterrows():
        for category in split_values(row.get("equipment_target_summary")):
            rows.append({
                "equipment_category": category,
                "iati_identifier": row.get("iati_identifier"),
                "country_codes": row.get("country_codes"),
                "funding_agencies": row.get("funding_agencies"),
                "reporting_org_name": row.get("reporting_org_name"),
                "activity_status_code": row.get("activity_status_code"),
                "total_budget_amount": safe_float(row.get("total_budget_amount")),
                "opportunity_score": safe_float(row.get("opportunity_score")),
                "priority_band": row.get("priority_band"),
                "predicted_tender_window": row.get("predicted_tender_window"),
            })

    if not rows:
        return pd.DataFrame(columns=columns)

    exploded = pd.DataFrame(rows)
    output = []

    for category, group in exploded.groupby("equipment_category"):
        countries = [
            country
            for value in group["country_codes"]
            for country in split_values(value)
        ]
        donors = [
            donor
            for value in group["funding_agencies"]
            for donor in split_values(value)
        ]

        if not donors:
            donors = [
                donor
                for donor in group["reporting_org_name"]
                if clean_text(donor)
            ]

        country_codes = join_unique(countries)

        output.append({
            "equipment_entity_id": stable_id("equip", category),
            "equipment_category": category,
            "activity_count": int(group["iati_identifier"].nunique()),
            "active_activity_count": int((group["activity_status_code"] == "2").sum()),
            "pipeline_activity_count": int((group["activity_status_code"] == "1").sum()),
            "reported_budget": round(group["total_budget_amount"].sum(), 2),
            "average_opportunity_score": round(group["opportunity_score"].mean(), 1),
            "high_priority_opportunities": int(
                group["priority_band"].isin([
                    "Strategic Priority",
                    "Qualified Lead",
                ]).sum()
            ),
            "country_codes": country_codes,
            "country_names": country_names_from_codes(country_codes),
            "top_donors": format_top(donors),
            "next_windows": format_top(group["predicted_tender_window"], limit=3),
            "source_layer": "canonical",
        })

    return (
        pd.DataFrame(output, columns=columns)
        .sort_values(
            by=["high_priority_opportunities", "reported_budget", "activity_count"],
            ascending=[False, False, False],
        )
        .reset_index(drop=True)
    )


def build_manufacturer_entities(opportunities: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "manufacturer_entity_id",
        "manufacturer_name",
        "manufacturer_aliases",
        "equipment_categories",
        "evidence_source",
        "activity_count",
        "top_countries",
        "source_layer",
    ]

    if opportunities.empty or "manufacturer_mentions" not in opportunities.columns:
        return pd.DataFrame(columns=columns)

    rows = []

    for _, row in opportunities.iterrows():
        for manufacturer in split_values(row.get("manufacturer_mentions")):
            rows.append({
                "manufacturer_name": manufacturer,
                "iati_identifier": row.get("iati_identifier"),
                "equipment_target_summary": row.get("equipment_target_summary"),
                "country_codes": row.get("country_codes"),
            })

    if not rows:
        return pd.DataFrame(columns=columns)

    exploded = pd.DataFrame(rows)
    output = []

    for manufacturer, group in exploded.groupby("manufacturer_name"):
        countries = [
            country
            for value in group["country_codes"]
            for country in split_values(value)
        ]
        equipment = [
            category
            for value in group["equipment_target_summary"]
            for category in split_values(value)
        ]
        output.append({
            "manufacturer_entity_id": stable_id("mfr", manufacturer),
            "manufacturer_name": manufacturer,
            "manufacturer_aliases": manufacturer,
            "equipment_categories": format_top(equipment),
            "evidence_source": "IATI activity text mention",
            "activity_count": int(group["iati_identifier"].nunique()),
            "top_countries": format_top(countries),
            "source_layer": "canonical",
        })

    return (
        pd.DataFrame(output, columns=columns)
        .sort_values(by=["activity_count", "manufacturer_name"], ascending=[False, True])
        .reset_index(drop=True)
    )


def build_opportunity_scores(opportunities: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "opportunity_score_id",
        "iati_identifier",
        "opportunity_score",
        "priority_band",
        "confidence",
        "signal_summary",
        "prediction_basis",
        "predicted_tender_window",
        "procurement_signal",
        "source_layer",
    ]

    if opportunities.empty:
        return pd.DataFrame(columns=columns)

    output = opportunities.copy()

    for column in columns:
        if column not in output.columns and column != "opportunity_score_id":
            output[column] = ""

    output["opportunity_score_id"] = output["iati_identifier"].apply(
        lambda value: stable_id("opp_score", value)
    )
    output["source_layer"] = "intelligence"

    return (
        output[columns]
        .sort_values(
            by=["opportunity_score", "confidence"],
            ascending=[False, False],
        )
        .reset_index(drop=True)
    )


def build_programme_intelligence(opportunities: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "programme_intelligence_id",
        "iati_identifier",
        "programme_name",
        "country_codes",
        "country_names",
        "funding_agencies",
        "implementing_partners",
        "activity_status_label",
        "sector_names",
        "total_budget_amount",
        "future_disbursement_amount",
        "future_budget_amount",
        "equipment_target_summary",
        "opportunity_score",
        "priority_band",
        "confidence",
        "predicted_tender_window",
        "tender_probability",
        "tender_stage",
        "tender_horizon",
        "recommended_action",
        "source_layer",
    ]

    if opportunities.empty:
        return pd.DataFrame(columns=columns)

    output = opportunities.copy()

    for column in [
        "country_codes",
        "country_names",
        "funding_agencies",
        "implementing_partners",
        "activity_status_label",
        "sector_names",
        "total_budget_amount",
        "future_disbursement_amount",
        "future_budget_amount",
        "equipment_target_summary",
        "opportunity_score",
        "priority_band",
        "confidence",
        "predicted_tender_window",
        "tender_probability",
        "tender_stage",
        "tender_horizon",
        "recommended_action",
    ]:
        if column not in output.columns:
            output[column] = ""

    output["programme_intelligence_id"] = output["iati_identifier"].apply(
        lambda value: stable_id("programme", value)
    )
    output["programme_name"] = output.get("project_title", "")
    output["source_layer"] = "intelligence"

    return (
        output[columns]
        .sort_values(
            by=["opportunity_score", "confidence", "total_budget_amount"],
            ascending=[False, False, False],
        )
        .reset_index(drop=True)
    )


def build_organisation_intelligence(
    organisation_entities: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "organisation_intelligence_id",
        "organisation_entity_id",
        "organisation_name",
        "account_type",
        "roles",
        "activity_count",
        "active_activity_count",
        "pipeline_activity_count",
        "country_codes",
        "country_names",
        "reported_budget",
        "average_opportunity_score",
        "high_priority_opportunities",
        "top_equipment_categories",
        "commercial_relevance",
        "latest_update",
        "source_layer",
    ]

    if organisation_entities.empty:
        return pd.DataFrame(columns=columns)

    output = organisation_entities.copy()
    output["organisation_intelligence_id"] = output["organisation_entity_id"].apply(
        lambda value: stable_id("org_intel", value)
    )
    output["organisation_name"] = output["canonical_name"]
    output["account_type"] = output["roles"].apply(classify_account_type)
    output["commercial_relevance"] = output.apply(
        lambda row: priority_tier(
            safe_float(row.get("average_opportunity_score")),
            int(safe_float(row.get("high_priority_opportunities"))),
        ),
        axis=1,
    )
    output["source_layer"] = "intelligence"

    for column in columns:
        if column not in output.columns:
            output[column] = ""

    output["_tier_rank"] = output["commercial_relevance"].map({
        "Tier 1": 1,
        "Tier 2": 2,
        "Tier 3": 3,
        "Monitor": 4,
    }).fillna(5)

    return (
        output
        .sort_values(
            by=["_tier_rank", "high_priority_opportunities", "reported_budget"],
            ascending=[True, False, False],
        )[columns]
        .reset_index(drop=True)
    )


def account_fit_score(row: pd.Series) -> float:
    score = safe_float(row.get("average_opportunity_score"))
    score += min(18, safe_float(row.get("high_priority_opportunities")) * 6)
    budget_for_score = max(0.0, safe_float(row.get("reported_budget")))
    score += min(12, math.log10(budget_for_score + 1) * 1.2)

    roles = set(split_values(row.get("roles")))

    if "funding" in roles:
        score += 8

    if "implementing" in roles or "accountable" in roles:
        score += 5

    if split_values(row.get("top_equipment_categories")):
        score += 5

    return round(max(0, min(100, score)), 1)


def target_account_action(row: pd.Series) -> str:
    tier = row.get("priority_tier", "")
    account_type = row.get("account_type", "Organisation")

    if tier == "Tier 1":
        return f"Open account plan for {account_type.lower()} route and map procurement stakeholders."

    if tier == "Tier 2":
        return "Validate decision makers and connect top programmes to likely tender portals."

    if tier == "Tier 3":
        return "Monitor programme updates and collect procurement contact evidence."

    return "Keep account on market watch until stronger funding or equipment signals appear."


def build_target_accounts(
    organisation_intelligence: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "target_account_id",
        "organisation_entity_id",
        "account_name",
        "account_type",
        "priority_tier",
        "fit_score",
        "country_codes",
        "country_names",
        "top_needs",
        "reported_budget",
        "high_priority_opportunities",
        "crm_stage",
        "recommended_action",
        "source_layer",
    ]

    if organisation_intelligence.empty:
        return pd.DataFrame(columns=columns)

    output = organisation_intelligence.copy()
    output["fit_score"] = output.apply(account_fit_score, axis=1)
    output["priority_tier"] = output.apply(
        lambda row: priority_tier(
            safe_float(row.get("fit_score")),
            int(safe_float(row.get("high_priority_opportunities"))),
        ),
        axis=1,
    )
    output["target_account_id"] = output["organisation_entity_id"].apply(
        lambda value: stable_id("acct", value)
    )
    output["account_name"] = output["organisation_name"]
    output["top_needs"] = output["top_equipment_categories"].apply(
        lambda value: value or "General health sector"
    )
    output["crm_stage"] = output["priority_tier"].map({
        "Tier 1": "Prioritise",
        "Tier 2": "Qualify",
        "Tier 3": "Research",
        "Monitor": "Monitor",
    })
    output["recommended_action"] = output.apply(target_account_action, axis=1)
    output["source_layer"] = "commercial"

    return (
        output[columns]
        .sort_values(
            by=["fit_score", "high_priority_opportunities", "reported_budget"],
            ascending=[False, False, False],
        )
        .reset_index(drop=True)
    )


def build_org_activity_lookup(organisations: pd.DataFrame) -> Dict[str, List[str]]:
    if organisations.empty:
        return {}

    work = organisations.copy()

    for column in ["activity_id", "org_ref", "org_name"]:
        if column not in work.columns:
            work[column] = ""

    lookup: Dict[str, List[str]] = {}

    for _, row in work.iterrows():
        entity_id = stable_id(
            "org",
            organisation_entity_key(row.get("org_ref"), row.get("org_name")),
        )
        activity_id = clean_text(row.get("activity_id"))

        if not activity_id:
            continue

        lookup.setdefault(entity_id, [])

        if activity_id not in lookup[entity_id]:
            lookup[entity_id].append(activity_id)

    return lookup


def top_related_opportunity(
    opportunities: pd.DataFrame,
    activity_ids: List[str],
) -> pd.Series:
    if opportunities.empty or not activity_ids:
        return pd.Series(dtype=object)

    related = opportunities[
        opportunities.get("iati_identifier", "").isin(activity_ids)
    ].copy()

    if related.empty:
        return pd.Series(dtype=object)

    related["opportunity_score"] = related["opportunity_score"].apply(safe_float)

    return related.sort_values(
        by=["opportunity_score", "confidence"],
        ascending=[False, False],
    ).iloc[0]


def build_engagements(
    target_accounts: pd.DataFrame,
    opportunities: pd.DataFrame,
    organisations: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "engagement_id",
        "target_account_id",
        "account_name",
        "engagement_type",
        "related_iati_identifier",
        "related_programme_title",
        "engagement_stage",
        "next_step",
        "due_quarter",
        "source_layer",
    ]

    if target_accounts.empty:
        return pd.DataFrame(columns=columns)

    lookup = build_org_activity_lookup(organisations)
    rows = []

    active_accounts = target_accounts[
        target_accounts["priority_tier"].isin(["Tier 1", "Tier 2", "Tier 3"])
    ].copy()

    for _, account in active_accounts.iterrows():
        activity_ids = lookup.get(account.get("organisation_entity_id"), [])
        opportunity = top_related_opportunity(opportunities, activity_ids)
        programme_id = opportunity.get("iati_identifier", "")
        programme_title = opportunity.get("project_title", "")
        engagement_type = (
            "Donor route mapping"
            if account.get("account_type") == "Donor"
            else "Partner qualification"
        )

        rows.append({
            "engagement_id": stable_id(
                "engagement",
                account.get("target_account_id"),
                programme_id,
                engagement_type,
            ),
            "target_account_id": account.get("target_account_id"),
            "account_name": account.get("account_name"),
            "engagement_type": engagement_type,
            "related_iati_identifier": programme_id,
            "related_programme_title": programme_title,
            "engagement_stage": account.get("crm_stage"),
            "next_step": account.get("recommended_action"),
            "due_quarter": opportunity.get("predicted_tender_window", "Monitor"),
            "source_layer": "commercial",
        })

    return pd.DataFrame(rows, columns=columns)


def build_crm_notes(
    engagements: pd.DataFrame,
    opportunities: pd.DataFrame,
    as_of: date,
) -> pd.DataFrame:
    columns = [
        "crm_note_id",
        "target_account_id",
        "account_name",
        "note_type",
        "note",
        "related_iati_identifier",
        "created_at",
        "source_layer",
    ]

    if engagements.empty:
        return pd.DataFrame(columns=columns)

    opportunity_lookup = (
        opportunities.set_index("iati_identifier")
        if not opportunities.empty and "iati_identifier" in opportunities.columns
        else pd.DataFrame()
    )
    rows = []

    for _, engagement in engagements.iterrows():
        activity_id = engagement.get("related_iati_identifier", "")
        opportunity = (
            opportunity_lookup.loc[activity_id]
            if activity_id and activity_id in opportunity_lookup.index
            else pd.Series(dtype=object)
        )
        score = safe_float(opportunity.get("opportunity_score"))
        band = opportunity.get("priority_band", "Monitor")
        signals = opportunity.get("signal_summary", "No scored signal summary")
        note = (
            f"{engagement.get('account_name')}: {engagement.get('related_programme_title')} "
            f"scores {score} ({band}). Signals: {signals}."
        )

        rows.append({
            "crm_note_id": stable_id(
                "note",
                engagement.get("target_account_id"),
                activity_id,
            ),
            "target_account_id": engagement.get("target_account_id"),
            "account_name": engagement.get("account_name"),
            "note_type": "Opportunity brief",
            "note": note,
            "related_iati_identifier": activity_id,
            "created_at": as_of.isoformat(),
            "source_layer": "commercial",
        })

    return pd.DataFrame(rows, columns=columns)


def build_recommended_actions(
    opportunities: pd.DataFrame,
    target_accounts: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "recommended_action_id",
        "target_account_id",
        "account_name",
        "iati_identifier",
        "programme_title",
        "priority_band",
        "opportunity_score",
        "action_type",
        "recommended_action",
        "action_owner",
        "action_status",
        "source_layer",
    ]

    if opportunities.empty:
        return pd.DataFrame(columns=columns)

    accounts_by_name = {}

    if not target_accounts.empty:
        for _, row in target_accounts.iterrows():
            accounts_by_name[clean_text(row.get("account_name")).lower()] = row

    rows = []
    filtered = opportunities[
        (opportunities.get("procurement_signal", "") == "Yes")
        | (opportunities.get("opportunity_score", pd.Series(dtype=str)).apply(safe_float) >= 40)
    ].copy()

    for _, row in filtered.iterrows():
        account = pd.Series(dtype=object)
        account_candidates = (
            split_values(row.get("funding_agencies"))
            + split_values(row.get("implementing_partners"))
            + [row.get("reporting_org_name", "")]
        )

        for candidate in account_candidates:
            matched = accounts_by_name.get(clean_text(candidate).lower())

            if matched is not None:
                account = matched
                break

        action_type = (
            "Tender watch"
            if row.get("procurement_signal") == "Yes"
            else "Programme nurture"
        )

        rows.append({
            "recommended_action_id": stable_id(
                "action",
                row.get("iati_identifier"),
                action_type,
            ),
            "target_account_id": account.get("target_account_id", ""),
            "account_name": account.get("account_name", ""),
            "iati_identifier": row.get("iati_identifier"),
            "programme_title": row.get("project_title"),
            "priority_band": row.get("priority_band"),
            "opportunity_score": row.get("opportunity_score"),
            "action_type": action_type,
            "recommended_action": row.get("recommended_action"),
            "action_owner": "Commercial",
            "action_status": "Open",
            "source_layer": "commercial",
        })

    if not rows:
        return pd.DataFrame(columns=columns)

    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values(
            by=["opportunity_score", "priority_band"],
            ascending=[False, True],
        )
        .reset_index(drop=True)
    )


def layer_counts(datasets: Dict[str, pd.DataFrame]) -> Dict[str, Dict[str, int]]:
    counts = {}

    for layer, names in LAYER_OUTPUTS.items():
        counts[layer] = {
            name: int(len(datasets[name]))
            for name in names
            if name in datasets
        }

    return counts


def write_sqlite_tables(
    db_path: Path,
    datasets: Dict[str, pd.DataFrame],
) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)

    try:
        for name, dataframe in datasets.items():
            dataframe.to_sql(
                name,
                connection,
                if_exists="replace",
                index=False,
            )

        metadata = pd.DataFrame([
            {
                "key": "intelligence_pipeline_version",
                "value": PIPELINE_VERSION,
            },
            {
                "key": "intelligence_generated_at",
                "value": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        ])
        metadata.to_sql(
            "intelligence_metadata",
            connection,
            if_exists="replace",
            index=False,
        )
        connection.commit()
    finally:
        connection.close()


def build_market_summary(
    opportunities: pd.DataFrame,
    donors: pd.DataFrame,
    equipment: pd.DataFrame,
    predictions: pd.DataFrame,
    manifest: Dict[str, object],
    as_of: date,
    counts_by_layer: Dict[str, Dict[str, int]],
) -> Dict[str, object]:
    total_budget = opportunities["total_budget_amount"].apply(safe_float).sum()
    future_disbursement = (
        opportunities["future_disbursement_amount"].apply(safe_float).sum()
    )
    future_budget = opportunities["future_budget_amount"].apply(safe_float).sum()

    country_counts: Dict[str, int] = {}

    for value in opportunities["country_codes"]:
        for country in split_values(value):
            country_counts[country] = country_counts.get(country, 0) + 1

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": as_of.isoformat(),
        "source_generated_at": manifest.get("generated_at", ""),
        "pipeline_version": PIPELINE_VERSION,
        "pipeline_layers": PIPELINE_LAYERS,
        "layer_counts": counts_by_layer,
        "currency_note": (
            "Amounts are source-reported nominal values and are not converted "
            "across currencies."
        ),
        "metrics": {
            "projects": int(len(opportunities)),
            "active_projects": int(
                (opportunities["activity_status_code"] == "2").sum()
            ),
            "pipeline_projects": int(
                (opportunities["activity_status_code"] == "1").sum()
            ),
            "reported_budget": round(total_budget, 2),
            "future_disbursement": round(future_disbursement, 2),
            "future_budget": round(future_budget, 2),
            "procurement_signal_projects": int(
                (opportunities["procurement_signal"] == "Yes").sum()
            ),
            "high_priority_opportunities": int(
                opportunities["priority_band"].isin([
                    "Strategic Priority",
                    "Qualified Lead",
                ]).sum()
            ),
            "donors": int(len(donors)),
            "equipment_categories": int(len(equipment)),
            "tender_predictions": int(len(predictions)),
            "likely_procurement": int(
                (opportunities.get("tender_stage", pd.Series(dtype=str)) == "Likely procurement").sum()
            ) if "tender_stage" in opportunities.columns else 0,
            "direct_equipment_projects": int(
                (opportunities.get("equipment_evidence", pd.Series(dtype=str)) == "direct_keyword").sum()
            ) if "equipment_evidence" in opportunities.columns else 0,
            "countries": int(len(country_counts)),
        },
        "top_countries": [
            {
                "country_code": code,
                "country_name": COUNTRY_NAMES.get(code, code),
                "project_count": count,
            }
            for code, count in sorted(
                country_counts.items(),
                key=lambda entry: (-entry[1], entry[0]),
            )[:10]
        ],
        "plan_progress": PLAN_PROGRESS,
    }


def update_manifest(
    path: Path,
    datasets: Dict[str, pd.DataFrame],
    normalized_datasets: Optional[Dict[str, pd.DataFrame]] = None,
) -> Dict[str, object]:
    manifest = {}

    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            manifest = json.load(handle)

    row_counts = dict(manifest.get("row_counts", {}))
    files = dict(manifest.get("files", {}))

    for name, dataframe in datasets.items():
        row_counts[name] = int(len(dataframe))
        files[name] = f"{name}.csv"

    for name, dataframe in (normalized_datasets or {}).items():
        if (path.parent / f"{name}.csv").exists():
            row_counts[name] = int(len(dataframe))
            files[name] = f"{name}.csv"

    manifest["pipeline_version"] = PIPELINE_VERSION
    manifest["intelligence_generated_at"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    manifest["row_counts"] = row_counts
    manifest["files"] = files
    manifest["plan_progress"] = PLAN_PROGRESS
    manifest["pipeline_layers"] = PIPELINE_LAYERS
    manifest["layer_outputs"] = LAYER_OUTPUTS

    with path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)

    return manifest


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir)
    as_of = as_of_date(args.as_of)

    activities = read_first_available_csv(
        data_dir,
        "activities.csv",
        "iati_health_projects.csv",
    )
    transactions = read_first_available_csv(data_dir, "transactions.csv")
    budgets = read_csv(data_dir / "budgets.csv")
    planned = read_csv(data_dir / "planned_disbursements.csv")
    organisations = read_first_available_csv(data_dir, "organisations.csv")

    manifest_path = data_dir / "manifest.json"

    if manifest_path.exists():
        with manifest_path.open("r", encoding="utf-8") as handle:
            source_manifest = json.load(handle)
    else:
        source_manifest = {}

    opportunities = build_opportunities(
        activities,
        transactions,
        budgets,
        planned,
        as_of,
    )

    organisation_entities = build_organisation_entities(
        organisations,
        opportunities,
    )
    organisation_aliases = build_organisation_aliases(organisations)
    equipment_entities = build_equipment_entities(opportunities)
    manufacturer_entities = build_manufacturer_entities(opportunities)

    opportunity_scores = build_opportunity_scores(opportunities)
    organisation_intelligence = build_organisation_intelligence(
        organisation_entities,
    )
    programme_intelligence = build_programme_intelligence(opportunities)
    donors = build_donor_intelligence(opportunities)
    equipment = build_equipment_intelligence(opportunities)
    predictions = build_tender_predictions(opportunities)

    datasets = {
        "organisation_entities": organisation_entities,
        "organisation_aliases": organisation_aliases,
        "equipment_entities": equipment_entities,
        "manufacturer_entities": manufacturer_entities,
        "opportunity_scores": opportunity_scores,
        "organisation_intelligence": organisation_intelligence,
        "programme_intelligence": programme_intelligence,
        "donor_intelligence": donors,
        "target_accounts": build_target_accounts(organisation_intelligence),
    }

    datasets["engagements"] = build_engagements(
        datasets["target_accounts"],
        opportunities,
        organisations,
    )
    datasets["crm_notes"] = build_crm_notes(
        datasets["engagements"],
        opportunities,
        as_of,
    )
    datasets["recommended_actions"] = build_recommended_actions(
        opportunities,
        datasets["target_accounts"],
    )

    legacy_datasets = {
        "opportunities": opportunities,
        "equipment_intelligence": equipment,
        "tender_predictions": predictions,
    }

    datasets.update(legacy_datasets)

    for name, dataframe in datasets.items():
        output_path = data_dir / f"{name}.csv"
        dataframe.to_csv(output_path, index=False)
        print(f"[intel] Saved {output_path} ({len(dataframe)} rows)")

    counts_by_layer = layer_counts({
        "activities": activities,
        "transactions": transactions,
        "organisations": organisations,
        **datasets,
    })

    summary = build_market_summary(
        opportunities,
        donors,
        equipment,
        predictions,
        source_manifest,
        as_of,
        counts_by_layer,
    )

    with (data_dir / "market_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False)

    updated_manifest = update_manifest(
        manifest_path,
        datasets,
        {
            "activities": activities,
            "transactions": transactions,
            "organisations": organisations,
        },
    )

    if not args.skip_sqlite:
        write_sqlite_tables(Path(args.database), datasets)
        print(f"[intel] SQLite intelligence tables saved: {args.database}")

    print(
        "[intel] Intelligence build complete: "
        f"{len(opportunities)} opportunities, "
        f"{summary['metrics']['high_priority_opportunities']} high priority, "
        f"{len(predictions)} tender predictions."
    )
    print(f"[intel] Manifest version: {updated_manifest['pipeline_version']}")


if __name__ == "__main__":
    main()


