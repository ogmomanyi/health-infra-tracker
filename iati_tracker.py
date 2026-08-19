#!/usr/bin/env python3

"""
IATI Health Sector Intelligence - Step 1
========================================

Builds a normalized, persistent data foundation from the IATI Datastore v3 API.

Outputs:

    data/iati_health_projects.csv
    data/transactions.csv
    data/budgets.csv
    data/planned_disbursements.csv
    data/activity_countries.csv
    data/organisations.csv
    data/iati_intelligence.db
    data/projects_state.json

The database is intentionally normalized so that future intelligence layers
can calculate:

    - funding velocity
    - budget growth
    - disbursement acceleration
    - procurement probability
    - opportunity scores
    - donor/implementer relationships
    - country market intelligence
    - competitor intelligence
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_URL = "https://api.iatistandard.org/datastore/activity/select"

TARGET_COUNTRIES = [
    "KE",
    "UG",
    "RW",
    "ET",
    "SS",
    "SO",
    "TZ",
    "CD",
]

SECTOR_CODES = {
    "12110": "Health policy and administrative management",
    "12181": "Medical education/training",
    "12182": "Medical research",
    "12191": "Medical services",
    "12196": "Health statistics and data",

    "12220": "Basic health care",
    "12230": "Basic health infrastructure",
    "12240": "Basic nutrition",
    "12250": "Infectious disease control",
    "12261": "Health education",
    "12262": "Malaria control",
    "12263": "Tuberculosis control",
    "12264": "COVID-19 control",
    "12281": "Health personnel development",

    "12310": "NCDs control, general",
    "12320": "Tobacco use control",
    "12330": "Control of harmful use of alcohol and drugs",
    "12340": "Promotion of mental health and well-being",
    "12350": "Other prevention and treatment of NCDs",
    "12382": "Research for prevention and control of NCDs",
}

ACTIVITY_STATUS_LABELS = {
    "1": "Stage 1: Pipeline / Planning / Approval",
    "2": "Stage 2: Implementation / Active",
    "3": "Finalisation",
    "4": "Closed",
    "5": "Cancelled",
    "6": "Suspended",
}

TARGET_STATUS_CODES = ["1", "2"]

ROLE_FUNDING = "1"
ROLE_ACCOUNTABLE = "2"
ROLE_IMPLEMENTING = "4"

DATE_PLANNED_START = "1"
DATE_ACTUAL_START = "2"
DATE_PLANNED_END = "3"
DATE_ACTUAL_END = "4"

EQUIPMENT_KEYWORDS = {
    "Medical Devices & Equipment": [
        r"medical device",
        r"medical equipment",
        r"biomedical equipment",
        r"laboratory equipment",
        r"lab equipment",
        r"surgical equipment",
        r"imaging equipment",
        r"x-?ray",
        r"\bmri\b",
        r"ultrasound",
        r"ventilator",
        r"incubator",
        r"autoclave",
        r"sterili[sz]",
    ],
    "Diagnostic Equipment": [
        r"diagnostic",
        r"rapid test",
        r"test kit",
        r"point.of.care",
        r"in.vitro diagnostic",
        r"\bivd\b",
        r"analy[sz]er",
        r"screening",
    ],
    "Cold Chain / Storage": [
        r"cold chain",
        r"cold storage",
        r"refrigerat",
        r"vaccine storage",
        r"\bfridge\b",
        r"freezer",
    ],
    "Vehicles & Transport": [
        r"ambulance",
        r"\bvehicles?\b",
        r"motorcycle",
        r"\b4x4\b",
        r"fleet of",
    ],
    "PPE": [
        r"personal protective equipment",
        r"\bppe\b",
        r"protective gear",
        r"\bgloves\b",
        r"\bmasks?\b",
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
    ],
}

_COMPILED_KEYWORDS = {
    category: [
        re.compile(pattern, re.IGNORECASE)
        for pattern in patterns
    ]
    for category, patterns in EQUIPMENT_KEYWORDS.items()
}


# ============================================================================
# GENERAL HELPERS
# ============================================================================

def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def as_list(item: Any) -> List[Any]:
    if item is None:
        return []

    if isinstance(item, list):
        return item

    return [item]


def text(node: Any) -> str:
    if isinstance(node, dict):
        return str(node.get("text()", "")).strip()

    if isinstance(node, str):
        return node.strip()

    return ""


def narrative_text(
    narrative_list: Optional[Union[List[dict], dict]],
    prefer_lang: str = "en",
) -> str:

    if not narrative_list:
        return ""

    if isinstance(narrative_list, dict):
        narrative_list = [narrative_list]

    fallback = ""

    for narrative in narrative_list:

        if not isinstance(narrative, dict):
            continue

        txt = text(narrative)

        if not txt:
            continue

        if not fallback:
            fallback = txt

        lang = (
            narrative.get("@xml:lang")
            or narrative.get("@xml\\:lang")
            or ""
        ).lower()

        if lang == prefer_lang or not lang:
            return txt

    return fallback


def clean_number(value: Any) -> Optional[float]:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ============================================================================
# ACTIVITY PARSING
# ============================================================================

def reporting_org(activity: dict) -> Tuple[str, str]:

    orgs = as_list(activity.get("reporting-org"))

    if not orgs:
        return "", ""

    org = orgs[0]

    if not isinstance(org, dict):
        return "", ""

    return (
        org.get("@ref", "") or "",
        narrative_text(org.get("narrative")),
    )


def participating_orgs(
    activity: dict,
    role_code: str,
) -> List[Dict[str, str]]:

    results = []

    for org in as_list(activity.get("participating-org")):

        if not isinstance(org, dict):
            continue

        if org.get("@role") != role_code:
            continue

        name = (
            narrative_text(org.get("narrative"))
            or org.get("@ref", "")
        )

        if not name:
            continue

        results.append({
            "ref": org.get("@ref", "") or "",
            "name": name,
            "type": org.get("@type", "") or "",
            "role": role_code,
        })

    return results


def activity_dates(activity: dict) -> Dict[str, str]:

    output = {}

    for item in as_list(activity.get("activity-date")):

        if not isinstance(item, dict):
            continue

        date_type = item.get("@type")

        if date_type:
            output[date_type] = item.get("@iso-date", "") or ""

    return output


def activity_title(activity: dict) -> str:

    titles = as_list(activity.get("title"))

    if not titles:
        return ""

    title = titles[0]

    if not isinstance(title, dict):
        return ""

    return narrative_text(title.get("narrative"))


def activity_descriptions(activity: dict) -> Tuple[str, str]:

    general = ""
    all_descriptions = []

    for item in as_list(activity.get("description")):

        if not isinstance(item, dict):
            continue

        value = narrative_text(item.get("narrative"))

        if not value:
            continue

        all_descriptions.append(value)

        if not general and item.get("@type") in (None, "1"):
            general = value

    if not general and all_descriptions:
        general = all_descriptions[0]

    return general, " ".join(all_descriptions)


def sectors(activity: dict) -> List[Dict[str, str]]:

    output = []

    for sector in as_list(activity.get("sector")):

        if not isinstance(sector, dict):
            continue

        code = sector.get("@code", "")

        if not code:
            continue

        name = (
            SECTOR_CODES.get(code)
            or narrative_text(sector.get("narrative"))
        )

        output.append({
            "code": code,
            "name": name,
            "vocabulary": sector.get("@vocabulary", "") or "",
        })

    return output


def recipient_countries(activity: dict) -> List[Dict[str, Any]]:

    output = []

    for country in as_list(activity.get("recipient-country")):

        if not isinstance(country, dict):
            continue

        code = country.get("@code", "")

        if not code:
            continue

        percentage = clean_number(
            country.get("@percentage")
        )

        output.append({
            "country_code": code,
            "percentage": percentage,
        })

    return output


# ============================================================================
# EQUIPMENT EXTRACTION
# ============================================================================

def extract_equipment_targets(
    *texts: str,
) -> Tuple[str, str]:

    haystack = " ".join(
        value for value in texts if value
    )

    if not haystack:
        return "", ""

    categories = []
    snippets = []

    for category, patterns in _COMPILED_KEYWORDS.items():

        for pattern in patterns:

            match = pattern.search(haystack)

            if not match:
                continue

            categories.append(category)

            start = max(0, match.start() - 75)
            end = min(len(haystack), match.end() + 100)

            snippet = haystack[start:end].strip()

            snippets.append(
                f"{category}: …{snippet}…"
            )

            break

    return (
        "; ".join(dict.fromkeys(categories)),
        " | ".join(snippets),
    )


# ============================================================================
# FINANCIAL PARSING
# ============================================================================

def parse_budgets(
    activity: dict,
    activity_id: str,
) -> List[Dict[str, Any]]:

    records = []

    for index, budget in enumerate(
        as_list(activity.get("budget"))
    ):

        if not isinstance(budget, dict):
            continue

        values = as_list(
            budget.get("value")
        )

        if not values:
            continue

        value = values[0]

        if not isinstance(value, dict):
            continue

        amount = clean_number(
            value.get("text()")
        )

        if amount is None:
            continue

        period_start = ""
        period_end = ""

        period_start_values = as_list(
            budget.get("period-start")
        )

        if period_start_values:
            first_period_start = period_start_values[0]

            if isinstance(
                first_period_start,
                dict,
            ):
                period_start = (
                    first_period_start.get(
                        "@iso-date",
                        "",
                    )
                    or ""
                )

        period_end_values = as_list(
            budget.get("period-end")
        )

        if period_end_values:
            first_period_end = period_end_values[0]

            if isinstance(
                first_period_end,
                dict,
            ):
                period_end = (
                    first_period_end.get(
                        "@iso-date",
                        "",
                    )
                    or ""
                )

        records.append({
            "activity_id": activity_id,

            "budget_index": index,

            "budget_type_code":
                budget.get(
                    "@type",
                    "",
                )
                or "",

            "budget_status_code":
                budget.get(
                    "@status",
                    "",
                )
                or "",

            "period_start":
                period_start,

            "period_end":
                period_end,

            "amount":
                amount,

            "currency":
                value.get(
                    "@currency",
                    "",
                )
                or "",

            "value_date":
                value.get(
                    "@value-date",
                    "",
                )
                or "",
        })

    return records


def parse_transactions(
    activity: dict,
    activity_id: str,
) -> List[Dict[str, Any]]:

    records = []

    for index, transaction in enumerate(
        as_list(activity.get("transaction"))
    ):

        if not isinstance(transaction, dict):
            continue

        transaction_type = as_list(
            transaction.get("transaction-type")
        )

        transaction_date = as_list(
            transaction.get("transaction-date")
        )

        values = as_list(
            transaction.get("value")
        )

        transaction_type_code = ""

        if transaction_type:
            first = transaction_type[0]

            if isinstance(first, dict):
                transaction_type_code = (
                    first.get("@code", "")
                    or ""
                )

        transaction_date_value = ""

        if transaction_date:
            first = transaction_date[0]

            if isinstance(first, dict):
                transaction_date_value = (
                    first.get("@iso-date", "")
                    or ""
                )

        if not values:
            continue

        value = values[0]

        if not isinstance(value, dict):
            continue

        amount = clean_number(
            value.get("text()")
        )

        if amount is None:
            continue

        provider = parse_org_node(
            transaction.get("provider-org")
        )

        receiver = parse_org_node(
            transaction.get("receiver-org")
        )

        description = narrative_text(
            transaction.get("description")
        )

        transaction_sector = parse_single_code(
            transaction.get("sector")
        )

        recipient_country = parse_single_code(
            transaction.get("recipient-country")
        )

        flow_type = parse_single_code(
            transaction.get("flow-type")
        )

        finance_type = parse_single_code(
            transaction.get("finance-type")
        )

        tied_status = parse_single_code(
            transaction.get("tied-status")
        )

        aid_types = []

        for aid_type in as_list(
            transaction.get("aid-type")
        ):

            if isinstance(aid_type, dict):
                code = aid_type.get("@code", "")

                if code:
                    aid_types.append(code)

        records.append({
            "activity_id": activity_id,
            "transaction_index": index,
            "transaction_ref": (
                transaction.get("@ref", "")
                or ""
            ),
            "humanitarian": (
                transaction.get("@humanitarian", "")
                or ""
            ),
            "transaction_type_code":
                transaction_type_code,
            "transaction_date":
                transaction_date_value,
            "amount":
                amount,
            "currency":
                value.get("@currency", "") or "",
            "value_date":
                value.get("@value-date", "") or "",
            "description":
                description,
            "provider_org_ref":
                provider["ref"],
            "provider_org_name":
                provider["name"],
            "provider_org_type":
                provider["type"],
            "provider_activity_id":
                provider["activity_id"],
            "receiver_org_ref":
                receiver["ref"],
            "receiver_org_name":
                receiver["name"],
            "receiver_org_type":
                receiver["type"],
            "receiver_activity_id":
                receiver["activity_id"],
            "sector_code":
                transaction_sector,
            "recipient_country_code":
                recipient_country,
            "flow_type_code":
                flow_type,
            "finance_type_code":
                finance_type,
            "aid_type_codes":
                "; ".join(aid_types),
            "tied_status_code":
                tied_status,
        })

    return records


def parse_planned_disbursements(
    activity: dict,
    activity_id: str,
) -> List[Dict[str, Any]]:

    records = []

    for index, item in enumerate(
        as_list(activity.get("planned-disbursement"))
    ):

        if not isinstance(item, dict):
            continue

        values = as_list(
            item.get("value")
        )

        if not values:
            continue

        value = values[0]

        if not isinstance(value, dict):
            continue

        amount = clean_number(
            value.get("text()")
        )

        if amount is None:
            continue

        period_start = get_nested_iso_date(
            item.get("period-start")
        )

        period_end = get_nested_iso_date(
            item.get("period-end")
        )

        provider = parse_org_node(
            item.get("provider-org")
        )

        receiver = parse_org_node(
            item.get("receiver-org")
        )

        records.append({
            "activity_id":
                activity_id,
            "planned_disbursement_index":
                index,
            "type_code":
                item.get("@type", "") or "",
            "period_start":
                period_start,
            "period_end":
                period_end,
            "amount":
                amount,
            "currency":
                value.get("@currency", "") or "",
            "value_date":
                value.get("@value-date", "") or "",
            "provider_org_ref":
                provider["ref"],
            "provider_org_name":
                provider["name"],
            "provider_org_type":
                provider["type"],
            "provider_activity_id":
                provider["activity_id"],
            "receiver_org_ref":
                receiver["ref"],
            "receiver_org_name":
                receiver["name"],
            "receiver_org_type":
                receiver["type"],
            "receiver_activity_id":
                receiver["activity_id"],
        })

    return records


def get_nested_iso_date(
    node: Any,
) -> str:

    items = as_list(node)

    if not items:
        return ""

    first = items[0]

    if isinstance(first, dict):
        return first.get("@iso-date", "") or ""

    return ""


def parse_single_code(
    node: Any,
) -> str:

    items = as_list(node)

    if not items:
        return ""

    first = items[0]

    if isinstance(first, dict):
        return first.get("@code", "") or ""

    return ""


def parse_org_node(
    node: Any,
) -> Dict[str, str]:

    items = as_list(node)

    if not items:
        return {
            "ref": "",
            "name": "",
            "type": "",
            "activity_id": "",
        }

    org = items[0]

    if not isinstance(org, dict):
        return {
            "ref": "",
            "name": "",
            "type": "",
            "activity_id": "",
        }

    return {
        "ref": org.get("@ref", "") or "",
        "name": (
            narrative_text(org.get("narrative"))
            or ""
        ),
        "type": org.get("@type", "") or "",
        "activity_id": (
            org.get("@provider-activity-id")
            or org.get("@receiver-activity-id")
            or ""
        ),
    }


# ============================================================================
# ACTIVITY PARSER
# ============================================================================

def resolve_activity_budget(
    budgets: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Resolve an activity-level budget without treating IATI versions as additive."""

    if not budgets:
        return {
            "total": None,
            "currency": "",
            "budget_type": "",
            "status": "NO_BUDGET",
            "confidence": "NONE",
        }

    original = [b for b in budgets if b.get("budget_type_code") == "1"]
    revised = [b for b in budgets if b.get("budget_type_code") == "2"]

    selected = revised or original or budgets
    selected_type = (
        "REVISED" if revised else
        "ORIGINAL" if original else
        "UNKNOWN"
    )

    def currencies_for(items: List[Dict[str, Any]]) -> set:
        return {
            str(b.get("currency") or "").strip().upper()
            for b in items
            if str(b.get("currency") or "").strip()
        }

    currencies = currencies_for(selected)

    if len(currencies) > 1:
        return {
            "total": None,
            "currency": "MIXED",
            "budget_type": selected_type,
            "status": "MIXED_CURRENCY",
            "confidence": "LOW",
        }

    currency = next(iter(currencies), "")

    net_total = sum(
        float(b["amount"])
        for b in selected
        if b.get("amount") is not None
    )

    if net_total > 0:
        return {
            "total": net_total,
            "currency": currency,
            "budget_type": selected_type,
            "status": "VALID",
            "confidence": "HIGH",
        }

    # Some publishers expose negative revision/adjustment lines.
    # Never pass a negative project budget into commercial scoring.
    positive_total = sum(
        float(b["amount"])
        for b in selected
        if b.get("amount") is not None and float(b["amount"]) > 0
    )

    if positive_total > 0:
        return {
            "total": positive_total,
            "currency": currency,
            "budget_type": selected_type,
            "status": "POSITIVE_COMPONENTS_ONLY",
            "confidence": "MEDIUM",
        }

    # Revised data can be negative-only while the original budget contains
    # the actual positive allocation. Use it as a safe fallback.
    if revised and original:
        original_currencies = currencies_for(original)
        original_positive = sum(
            float(b["amount"])
            for b in original
            if b.get("amount") is not None and float(b["amount"]) > 0
        )
        if len(original_currencies) == 1 and original_positive > 0:
            return {
                "total": original_positive,
                "currency": next(iter(original_currencies)),
                "budget_type": "ORIGINAL_FALLBACK",
                "status": "REVISED_NEGATIVE_OR_EMPTY",
                "confidence": "MEDIUM",
            }

    return {
        "total": None,
        "currency": currency,
        "budget_type": selected_type,
        "status": "NO_POSITIVE_BUDGET",
        "confidence": "LOW",
    }


def parse_activity(
    raw_doc: dict,
) -> Optional[Dict[str, Any]]:

    blob = raw_doc.get(
        "iati_json",
        raw_doc,
    )

    if isinstance(blob, str):

        try:
            blob = json.loads(blob)
        except json.JSONDecodeError:
            return None

    if not isinstance(blob, dict):
        return None

    activities = as_list(
        blob.get("iati-activity")
    )

    if not activities:
        return None

    activity = activities[0]

    if not isinstance(activity, dict):
        return None

    identifiers = as_list(
        activity.get("iati-identifier")
    )

    if not identifiers:
        return None

    activity_id = text(
        identifiers[0]
    )

    if not activity_id:
        return None

    reporting_ref, reporting_name = reporting_org(
        activity
    )

    funding = participating_orgs(
        activity,
        ROLE_FUNDING,
    )

    implementing = participating_orgs(
        activity,
        ROLE_IMPLEMENTING,
    )

    accountable = participating_orgs(
        activity,
        ROLE_ACCOUNTABLE,
    )

    status_items = as_list(
        activity.get("activity-status")
    )

    status_code = ""

    if status_items:
        if isinstance(status_items[0], dict):
            status_code = (
                status_items[0].get("@code", "")
                or ""
            )

    dates = activity_dates(activity)

    sectors_data = sectors(activity)

    countries_data = recipient_countries(
        activity
    )

    title = activity_title(activity)

    description, scan_text = activity_descriptions(
        activity
    )

    equipment_categories, equipment_snippets = (
        extract_equipment_targets(
            title,
            description,
            scan_text,
        )
    )

    first_budget = (
        parse_budgets(
            activity,
            activity_id,
        )
    )

    budget_resolution = resolve_activity_budget(
    first_budget
    )

    total_budget = budget_resolution["total"]
    budget_currency = budget_resolution["currency"]

    humanitarian = (
        activity.get("@humanitarian", "")
        or ""
    )

    return {
        "iati_identifier":
            activity_id,

        "project_title":
            title,

        "reporting_org_ref":
            reporting_ref,

        "reporting_org_name":
            reporting_name,

        "funding_agencies":
            "; ".join(
                item["name"]
                for item in funding
            ),

        "implementing_partners":
            "; ".join(
                item["name"]
                for item in implementing
            ),

        "accountable_orgs":
            "; ".join(
                item["name"]
                for item in accountable
            ),

        "funding_org_refs":
            "; ".join(
                item["ref"]
                for item in funding
                if item["ref"]
            ),

        "implementing_org_refs":
            "; ".join(
                item["ref"]
                for item in implementing
                if item["ref"]
            ),

        "country_codes":
            "; ".join(
                item["country_code"]
                for item in countries_data
            ),

        "country_percentages":
            "; ".join(
                f"{item['country_code']}:{item['percentage']}"
                for item in countries_data
                if item["percentage"] is not None
            ),

        "activity_status_code":
            status_code,

        "activity_status_label":
            ACTIVITY_STATUS_LABELS.get(
                status_code,
                status_code,
            ),

        "planned_start_date":
            dates.get(
                DATE_PLANNED_START,
                "",
            ),

        "actual_start_date":
            dates.get(
                DATE_ACTUAL_START,
                "",
            ),

        "planned_end_date":
            dates.get(
                DATE_PLANNED_END,
                "",
            ),

        "actual_end_date":
            dates.get(
                DATE_ACTUAL_END,
                "",
            ),

        "last_updated":
            activity.get(
                "@last-updated",
                "",
            )
            or "",

        "default_currency":
            activity.get(
                "@default-currency",
                "",
            )
            or "",

        "humanitarian":
            humanitarian,

        "default_flow_type_code":
            activity.get(
                "@default-flow-type",
                "",
            )
            or "",

        "default_finance_type_code":
            activity.get(
                "@default-finance-type",
                "",
            )
            or "",

        "default_aid_type_code":
            activity.get(
                "@default-aid-type",
                "",
            )
            or "",

        "default_tied_status_code":
            activity.get(
                "@default-tied-status",
                "",
            )
            or "",

        "total_budget_amount":
            total_budget if first_budget else None,

        "budget_currency":
            budget_currency,

        "budget_line_count":
            len(first_budget),

        "sector_codes":
            "; ".join(
                item["code"]
                for item in sectors_data
            ),

        "sector_names":
            "; ".join(
                item["name"]
                for item in sectors_data
                if item["name"]
            ),

        "description":
            description,

        "equipment_target_summary":
            equipment_categories,

        "equipment_target_snippets":
            equipment_snippets,

        "data_retrieved_at":
            now_utc(),
    }


# ============================================================================
# API
# ============================================================================

def build_query(
    countries: List[str],
    sector_codes: List[str],
    status_codes: List[str],
) -> str:

    country_clause = (
        f"recipient_country_code:"
        f"({' '.join(countries)})"
    )

    sector_clause = (
        f"sector_code:"
        f"({' '.join(sector_codes)})"
    )

    status_clause = (
        f"activity_status_code:"
        f"({' '.join(status_codes)})"
    )

    return (
        f"{country_clause} "
        f"AND {sector_clause} "
        f"AND {status_clause}"
    )


def create_session() -> requests.Session:

    retry = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[
            429,
            500,
            502,
            503,
            504,
        ],
        allowed_methods=["GET"],
    )

    session = requests.Session()

    session.mount(
        "https://",
        HTTPAdapter(
            max_retries=retry
        ),
    )

    return session


def fetch_all_activities(
    query: str,
    api_key: str,
    rows_per_page: int,
    max_pages: int,
    sleep_seconds: float,
    dump_raw_path: Optional[str],
) -> List[dict]:

    session = create_session()

    headers = {
        "Ocp-Apim-Subscription-Key":
            api_key
    }

    documents = []

    start = 0
    total_found = None
    page = 0

    while True:

        params = {
            "q": query,
            "fl": "iati_json",
            "wt": "json",
            "rows": rows_per_page,
            "start": start,
        }

        response = session.get(
            BASE_URL,
            headers=headers,
            params=params,
            timeout=90,
        )

        if response.status_code == 401:
            raise RuntimeError(
                "401 Unauthorized. "
                "Verify IATI_API_KEY."
            )

        response.raise_for_status()

        payload = response.json()

        if page == 0 and dump_raw_path:

            dump_path = Path(
                dump_raw_path
            )

            dump_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with dump_path.open(
                "w",
                encoding="utf-8",
            ) as handle:

                json.dump(
                    payload,
                    handle,
                    indent=2,
                    ensure_ascii=False,
                )

        response_block = payload.get(
            "response",
            {},
        )

        if total_found is None:

            total_found = response_block.get(
                "numFound",
                0,
            )

            print(
                f"[iati] API query matched "
                f"{total_found} activities."
            )

        page_docs = response_block.get(
            "docs",
            [],
        )

        documents.extend(
            page_docs
        )

        print(
            f"[iati] Page {page + 1}: "
            f"{len(page_docs)} records "
            f"({len(documents)}/{total_found})"
        )

        page += 1
        start += rows_per_page

        if (
            not page_docs
            or start >= total_found
            or page >= max_pages
        ):
            break

        time.sleep(
            sleep_seconds
        )

    return documents


# ============================================================================
# NORMALIZED DATASET BUILDER
# ============================================================================

def build_datasets(
    raw_docs: List[dict],
) -> Tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:

    activity_records = []
    transaction_records = []
    budget_records = []
    planned_records = []
    country_records = []
    organisation_records = []

    for raw_doc in raw_docs:

        parsed = parse_activity(
            raw_doc
        )

        if not parsed:
            continue

        activity_records.append(
            parsed
        )

        blob = raw_doc.get(
            "iati_json",
            raw_doc,
        )

        if isinstance(blob, str):

            try:
                blob = json.loads(blob)
            except json.JSONDecodeError:
                continue

        activities = as_list(
            blob.get("iati-activity")
        )

        if not activities:
            continue

        activity = activities[0]

        activity_id = parsed[
            "iati_identifier"
        ]

        # Transactions
        transaction_records.extend(
            parse_transactions(
                activity,
                activity_id,
            )
        )

        # Budgets
        budget_records.extend(
            parse_budgets(
                activity,
                activity_id,
            )
        )

        # Planned disbursements
        planned_records.extend(
            parse_planned_disbursements(
                activity,
                activity_id,
            )
        )

        # Recipient countries
        for country in recipient_countries(
            activity
        ):

            country_records.append({
                "activity_id":
                    activity_id,

                "country_code":
                    country["country_code"],

                "percentage":
                    country["percentage"],
            })

        # Organisations
        reporting_ref, reporting_name = (
            reporting_org(activity)
        )

        if reporting_ref or reporting_name:

            organisation_records.append({
                "activity_id":
                    activity_id,
                "org_ref":
                    reporting_ref,
                "org_name":
                    reporting_name,
                "role":
                    "reporting",
                "org_type":
                    "",
            })

        for role_code, role_name in [
            (ROLE_FUNDING, "funding"),
            (ROLE_IMPLEMENTING, "implementing"),
            (ROLE_ACCOUNTABLE, "accountable"),
        ]:

            for org in participating_orgs(
                activity,
                role_code,
            ):

                organisation_records.append({
                    "activity_id":
                        activity_id,
                    "org_ref":
                        org["ref"],
                    "org_name":
                        org["name"],
                    "role":
                        role_name,
                    "org_type":
                        org["type"],
                })

    activities_df = pd.DataFrame(
        activity_records
    )

    transactions_df = pd.DataFrame(
        transaction_records
    )

    budgets_df = pd.DataFrame(
        budget_records
    )

    planned_df = pd.DataFrame(
        planned_records
    )

    countries_df = pd.DataFrame(
        country_records
    )

    organisations_df = pd.DataFrame(
        organisation_records
    )

    if not activities_df.empty:

        activities_df = (
            activities_df
            .drop_duplicates(
                subset=[
                    "iati_identifier"
                ]
            )
            .reset_index(drop=True)
        )

    return (
        activities_df,
        transactions_df,
        budgets_df,
        planned_df,
        countries_df,
        organisations_df,
    )


# ============================================================================
# SQLITE STORAGE
# ============================================================================

def save_dataframe_to_sqlite(
    df: pd.DataFrame,
    table_name: str,
    connection: sqlite3.Connection,
) -> None:

    if df.empty:
        return

    df.to_sql(
        table_name,
        connection,
        if_exists="replace",
        index=False,
    )


def save_database(
    db_path: str,
    activities_df: pd.DataFrame,
    transactions_df: pd.DataFrame,
    budgets_df: pd.DataFrame,
    planned_df: pd.DataFrame,
    countries_df: pd.DataFrame,
    organisations_df: pd.DataFrame,
) -> None:

    path = Path(db_path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        path
    )

    try:

        save_dataframe_to_sqlite(
            activities_df,
            "activities",
            connection,
        )

        save_dataframe_to_sqlite(
            transactions_df,
            "transactions",
            connection,
        )

        save_dataframe_to_sqlite(
            budgets_df,
            "budgets",
            connection,
        )

        save_dataframe_to_sqlite(
            planned_df,
            "planned_disbursements",
            connection,
        )

        save_dataframe_to_sqlite(
            countries_df,
            "activity_countries",
            connection,
        )

        save_dataframe_to_sqlite(
            organisations_df,
            "organisations",
            connection,
        )

        metadata = pd.DataFrame([
            {
                "key": "last_pipeline_run",
                "value": now_utc(),
            },
            {
                "key": "pipeline_version",
                "value": "1.0-step1",
            },
            {
                "key": "countries",
                "value": ",".join(
                    TARGET_COUNTRIES
                ),
            },
        ])

        save_dataframe_to_sqlite(
            metadata,
            "metadata",
            connection,
        )

        connection.commit()

    finally:
        connection.close()


# ============================================================================
# CSV OUTPUT
# ============================================================================

def save_csvs(
    output_dir: str,
    datasets: Dict[str, pd.DataFrame],
) -> None:

    path = Path(output_dir)

    path.mkdir(
        parents=True,
        exist_ok=True,
    )

    for name, dataframe in datasets.items():

        output_path = (
            path / f"{name}.csv"
        )

        dataframe.to_csv(
            output_path,
            index=False,
        )

        print(
            f"[iati] Saved "
            f"{output_path} "
            f"({len(dataframe)} rows)"
        )


# ============================================================================
# DAILY SNAPSHOT
# ============================================================================

def save_daily_snapshot(
    snapshot_root: str,
    datasets: Dict[str, pd.DataFrame],
) -> None:

    date_string = (
        datetime.now(timezone.utc)
        .strftime("%Y-%m-%d")
    )

    snapshot_dir = (
        Path(snapshot_root)
        / date_string
    )

    snapshot_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    for name, dataframe in datasets.items():

        dataframe.to_csv(
            snapshot_dir / f"{name}.csv",
            index=False,
        )

    manifest = {
        "snapshot_date":
            date_string,

        "created_at":
            now_utc(),

        "row_counts": {
            name: len(dataframe)
            for name, dataframe
            in datasets.items()
        },
    }

    with (
        snapshot_dir
        / "manifest.json"
    ).open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            manifest,
            handle,
            indent=2,
        )


# ============================================================================
# DELTA STATE
# ============================================================================

def load_state(
    state_file: str,
) -> Dict[str, Any]:

    path = Path(state_file)

    if not path.exists():
        return {}

    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:

        return json.load(handle)


def save_state(
    state_file: str,
    activities_df: pd.DataFrame,
) -> None:

    state = {}

    for _, row in activities_df.iterrows():

        activity_id = row[
            "iati_identifier"
        ]

        budget = row[
            "total_budget_amount"
        ]

        if pd.isna(budget):
            budget = 0.0

        state[activity_id] = {
            "title":
                row.get(
                    "project_title",
                    "",
                ),

            "status":
                str(
                    row.get(
                        "activity_status_code",
                        "",
                    )
                ),

            "budget":
                float(budget),

            "budget_currency":
                row.get(
                    "budget_currency",
                    "",
                ),

            "equipment_tags":
                [
                    tag.strip()
                    for tag in str(
                        row.get(
                            "equipment_target_summary",
                            "",
                        )
                    ).split(";")
                    if tag.strip()
                ],

            "last_updated":
                row.get(
                    "last_updated",
                    "",
                ),

            "snapshot_timestamp":
                now_utc(),
        }

    path = Path(state_file)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            state,
            handle,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================================
# MANIFEST
# ============================================================================

def save_manifest(
    output_dir: str,
    datasets: Dict[str, pd.DataFrame],
    query: str,
) -> None:

    manifest = {
        "pipeline_version":
            "1.0-step1",

        "generated_at":
            now_utc(),

        "countries":
            TARGET_COUNTRIES,

        "query":
            query,

        "row_counts": {
            name:
                len(dataframe)
            for name, dataframe
            in datasets.items()
        },

        "files": {
            name:
                f"{name}.csv"
            for name
            in datasets
        },
    }

    path = (
        Path(output_dir)
        / "manifest.json"
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            manifest,
            handle,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "IATI Health Intelligence "
            "Step 1 Data Foundation"
        )
    )

    parser.add_argument(
    "--api-key",
    default=os.environ.get("IATI_API_KEY"),
    )

    parser.add_argument(
        "--countries",
        nargs="+",
        default=TARGET_COUNTRIES,
    )

    parser.add_argument(
        "--statuses",
        nargs="+",
        default=TARGET_STATUS_CODES,
    )

    parser.add_argument(
        "--rows",
        type=int,
        default=1000,
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=50,
    )

    parser.add_argument(
        "--sleep",
        type=float,
        default=13.0,
    )

    parser.add_argument(
        "--output-dir",
        default="data",
    )

    parser.add_argument(
        "--database",
        default="data/iati_intelligence.db",
    )

    parser.add_argument(
        "--state-file",
        default="data/projects_state.json",
    )

    parser.add_argument(
        "--snapshot-dir",
        default="data/history",
    )

    parser.add_argument(
        "--dump-raw",
        metavar="PATH",
    )

    parser.add_argument(
        "--mock",
        action="store_true",
    )

    args = parser.parse_args()

    # ------------------------------------------------------------------
    # MOCK MODE
    # ------------------------------------------------------------------

    if args.mock:

        print(
            "[iati] Running in mock mode."
        )

        raw_docs = [{
            "iati_json": {
                "iati-activity": [{
                    "iati-identifier": [{
                        "text()":
                            "XM-DAC-41114-KE-001"
                    }],

                    "reporting-org": [{
                        "@ref":
                            "GB-GOV-1",

                        "narrative": [{
                            "text()":
                                "Global Fund"
                        }]
                    }],

                    "title": [{
                        "narrative": [{
                            "text()":
                                "Western Kenya Hospital Cold Chain and ICU Diagnostic Upgrade"
                        }]
                    }],

                    "description": [{
                        "narrative": [{
                            "text()":
                                "Procuring cold storage refrigerators, 4 ambulances, laboratory equipment and diagnostic test kits."
                        }]
                    }],

                    "activity-status": [{
                        "@code": "2"
                    }],

                    "activity-date": [
                        {
                            "@type": "1",
                            "@iso-date":
                                "2025-01-01",
                        },
                        {
                            "@type": "3",
                            "@iso-date":
                                "2027-12-31",
                        },
                    ],

                    "recipient-country": [
                        {
                            "@code": "KE",
                            "@percentage": "100",
                        }
                    ],

                    "sector": [{
                        "@code": "12230"
                    }],

                    "budget": [{
                        "@type": "1",
                        "@status": "1",
                        "period-start": [{
                            "@iso-date":
                                "2026-01-01"
                        }],
                        "period-end": [{
                            "@iso-date":
                                "2026-12-31"
                        }],
                        "value": [{
                            "@currency": "USD",
                            "@value-date":
                                "2026-01-01",
                            "text()":
                                "1500000"
                        }]
                    }],

                    "transaction": [{
                        "@ref":
                            "TX001",

                        "transaction-type": [{
                            "@code": "3"
                        }],

                        "transaction-date": [{
                            "@iso-date":
                                "2026-06-01"
                        }],

                        "value": [{
                            "@currency": "USD",
                            "@value-date":
                                "2026-06-01",
                            "text()":
                                "350000"
                        }],

                        "description": [{
                            "narrative": [{
                                "text()":
                                    "First disbursement for laboratory equipment procurement."
                            }]
                        }],

                        "provider-org": [{
                            "@ref":
                                "GB-GOV-1",

                            "narrative": [{
                                "text()":
                                    "Global Fund"
                            }]
                        }],

                        "receiver-org": [{
                            "@ref":
                                "KE-MOH",

                            "narrative": [{
                                "text()":
                                    "Kenya Ministry of Health"
                            }]
                        }],

                        "recipient-country": [{
                            "@code":
                                "KE"
                        }],

                        "finance-type": [{
                            "@code":
                                "110"
                        }],

                        "aid-type": [{
                            "@code":
                                "A01"
                        }]
                    }],

                    "planned-disbursement": [{
                        "@type": "1",

                        "period-start": [{
                            "@iso-date":
                                "2026-10-01"
                        }],

                        "period-end": [{
                            "@iso-date":
                                "2026-12-31"
                        }],

                        "value": [{
                            "@currency": "USD",
                            "@value-date":
                                "2026-10-01",
                            "text()":
                                "500000"
                        }],

                        "provider-org": [{
                            "@ref":
                                "GB-GOV-1",

                            "narrative": [{
                                "text()":
                                    "Global Fund"
                            }]
                        }],

                        "receiver-org": [{
                            "@ref":
                                "KE-MOH",

                            "narrative": [{
                                "text()":
                                    "Kenya Ministry of Health"
                            }]
                        }]
                    }]
                }]
            }
        }]

    else:

        if not args.api_key:

            print(
                "[iati] ERROR: Missing API key.",
                file=sys.stderr,
            )

            sys.exit(1)

        query = build_query(
            args.countries,
            list(SECTOR_CODES.keys()),
            args.statuses,
        )

        raw_docs = fetch_all_activities(
            query,
            args.api_key,
            args.rows,
            args.max_pages,
            args.sleep,
            args.dump_raw,
        )

    # ------------------------------------------------------------------
    # BUILD DATASETS
    # ------------------------------------------------------------------

    (
        activities_df,
        transactions_df,
        budgets_df,
        planned_df,
        countries_df,
        organisations_df,
    ) = build_datasets(
        raw_docs
    )

    datasets = {
        "iati_health_projects":
            activities_df,

        "transactions":
            transactions_df,

        "budgets":
            budgets_df,

        "planned_disbursements":
            planned_df,

        "activity_countries":
            countries_df,

        "organisations":
            organisations_df,
    }

    print()
    print(
        "=========================================="
    )
    print(
        "IATI DATA FOUNDATION"
    )
    print(
        "=========================================="
    )

    for name, dataframe in datasets.items():

        print(
            f"{name:25} "
            f"{len(dataframe):>8,} rows"
        )

    print(
        "=========================================="
    )

    # ------------------------------------------------------------------
    # SAVE CURRENT DATA
    # ------------------------------------------------------------------

    save_csvs(
        args.output_dir,
        datasets,
    )

    # ------------------------------------------------------------------
    # SAVE SQLITE DATABASE
    # ------------------------------------------------------------------

    save_database(
        args.database,
        activities_df,
        transactions_df,
        budgets_df,
        planned_df,
        countries_df,
        organisations_df,
    )

    print(
        f"[iati] Database saved: "
        f"{args.database}"
    )

    # ------------------------------------------------------------------
    # SAVE DAILY SNAPSHOT
    # ------------------------------------------------------------------

    save_daily_snapshot(
        args.snapshot_dir,
        datasets,
    )

    # ------------------------------------------------------------------
    # SAVE STATE
    # ------------------------------------------------------------------

    save_state(
        args.state_file,
        activities_df,
    )

    # ------------------------------------------------------------------
    # SAVE MANIFEST
    # ------------------------------------------------------------------

    query = build_query(
        args.countries,
        list(SECTOR_CODES.keys()),
        args.statuses,
    )

    save_manifest(
        args.output_dir,
        datasets,
        query,
    )

    print()
    print(
        "[iati] Step 1 pipeline complete."
    )


if __name__ == "__main__":
    main()
