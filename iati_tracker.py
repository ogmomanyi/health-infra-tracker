#!/usr/bin/env python3
"""
IATI Health Sector Project Intelligence & Continuous Tracking Pipeline
======================================================================

Queries the IATI Datastore v3 API for health-sector development/humanitarian
activities across East & Central Africa (KE, UG, RW, ET, SS, SO, TZ, CD).

Features:
  - Preserves nested schema integrity (`fl=iati_json`) for linked budgets/dates.
  - Defensively normalizes XML-to-JSON object/list conversions.
  - Scans narratives for equipment procurement keywords and extracts text snippets.
  - Supports continuous delta tracking & Webhook alerting (Slack/Teams).
"""

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =========================================================================
# CONFIGURATION & CONSTANTS
# =========================================================================

BASE_URL = "https://api.iatistandard.org/datastore/activity/select"

TARGET_COUNTRIES = ["KE", "UG", "RW", "ET", "SS", "SO", "TZ", "CD"]

# OECD DAC CRS 5-digit health sector purpose codes
SECTOR_CODES: Dict[str, str] = {
    # 121 - Health, General
    "12110": "Health policy and administrative management",
    "12181": "Medical education/training",
    "12182": "Medical research",
    "12191": "Medical services",
    "12196": "Health statistics and data",
    # 122 - Basic Health
    "12220": "Basic health care",
    "12230": "Basic health infrastructure",
    "12240": "Basic nutrition",
    "12250": "Infectious disease control",
    "12261": "Health education",
    "12262": "Malaria control",
    "12263": "Tuberculosis control",
    "12264": "COVID-19 control",
    "12281": "Health personnel development",
    # 123 - Non-communicable diseases (NCDs)
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

EQUIPMENT_KEYWORDS: Dict[str, List[str]] = {
    "Medical Devices & Equipment": [
        r"medical device", r"medical equipment", r"biomedical equipment",
        r"laboratory equipment", r"lab equipment", r"surgical equipment",
        r"imaging equipment", r"x-?ray", r"ultrasound", r"\bmri\b",
        r"ventilator", r"incubator", r"autoclave", r"sterili[sz]",
    ],
    "Diagnostic Equipment": [
        r"diagnostic", r"rapid test", r"test kit", r"point.of.care",
        r"in.vitro diagnostic", r"\bivd\b", r"analy[sz]er", r"screening",
    ],
    "Cold Chain / Storage": [
        r"cold chain", r"cold storage", r"refrigerat", r"vaccine storage",
        r"\bfridge", r"freezer",
    ],
    "Vehicles & Transport": [
        r"ambulance", r"\bvehicles?\b", r"motorcycle", r"\b4x4\b", r"fleet of",
    ],
    "PPE": [
        r"personal protective equipment", r"\bppe\b", r"protective gear",
        r"\bgloves\b", r"\bmasks?\b", r"protective clothing",
    ],
    "Facility Infrastructure": [
        r"construction", r"renovation", r"rehabilitat", r"health facilit",
        r"hospital building", r"clinic\b", r"dispensary", r"dispensaries",
        r"infrastructure",
    ],
    "IT / Health Information Systems": [
        r"health information system", r"\bhmis\b", r"electronic medical record",
        r"\bemr\b", r"\behr\b", r"digital health", r"data system",
        r"software platform",
    ],
}
_COMPILED_KEYWORDS = {
    category: [re.compile(p, re.IGNORECASE) for p in patterns]
    for category, patterns in EQUIPMENT_KEYWORDS.items()
}

# =========================================================================
# UTILITIES & PARSING HELPERS
# =========================================================================

def _as_list(item: Any) -> List[Any]:
    """Ensures single elements XML-parsed as dicts are safely treated as lists."""
    if item is None:
        return []
    if isinstance(item, list):
        return item
    return [item]


def _text(node: Any) -> str:
    if isinstance(node, dict):
        return str(node.get("text()", "")).strip()
    elif isinstance(node, str):
        return node.strip()
    return ""


def _narrative_text(narrative_list: Optional[List[dict]], prefer_lang: str = "en") -> str:
    if not narrative_list:
        return ""
    fallback = ""
    for n in narrative_list:
        txt = _text(n)
        if not txt:
            continue
        if not fallback:
            fallback = txt
            
        # FIX: 'or ""' ensures that if get() returns None, it becomes a string before .lower()
        lang = (n.get("@xml:lang") or "").lower()
        
        if lang == prefer_lang or not lang:
            return txt
    return fallback


def _reporting_org(activity: dict) -> Tuple[str, str]:
    ro_list = _as_list(activity.get("reporting-org"))
    if not ro_list:
        return "", ""
    ro = ro_list[0]
    if isinstance(ro, dict):
        return ro.get("@ref", "") or "", _narrative_text(ro.get("narrative"))
    return "", ""


def _participating_orgs_by_role(activity: dict, role_code: str) -> List[str]:
    names = []
    for po in _as_list(activity.get("participating-org")):
        if isinstance(po, dict) and po.get("@role") == role_code:
            name = _narrative_text(po.get("narrative")) or po.get("@ref", "")
            if name:
                names.append(name)
    return names


def _activity_dates(activity: dict) -> Dict[str, str]:
    out = {}
    for ad in _as_list(activity.get("activity-date")):
        if isinstance(ad, dict):
            dtype = ad.get("@type")
            if dtype:
                out[dtype] = ad.get("@iso-date", "")
    return out


def _total_budget(activity: dict) -> Tuple[Optional[float], str, int]:
    totals: Dict[str, float] = defaultdict(float)
    n = 0
    for b in _as_list(activity.get("budget")):
        if not isinstance(b, dict):
            continue
        value_list = _as_list(b.get("value"))
        if not value_list:
            continue
        v = value_list[0]
        if isinstance(v, dict):
            try:
                amount = float(v.get("text()", 0) or 0)
            except (TypeError, ValueError):
                continue
            currency = v.get("@currency", "") or "USD"
            totals[currency] += amount
            n += 1

    if not totals:
        return None, "", 0
    if len(totals) == 1:
        currency, amount = next(iter(totals.items()))
        return amount, currency, n
    dominant = max(totals, key=totals.get)
    return totals[dominant], "MIXED", n


def _sectors(activity: dict) -> List[Tuple[str, str]]:
    out = []
    for s in _as_list(activity.get("sector")):
        if isinstance(s, dict):
            code = s.get("@code", "")
            if not code:
                continue
            name = SECTOR_CODES.get(code) or _narrative_text(s.get("narrative"))
            out.append((code, name))
    return out


def _recipient_countries(activity: dict) -> List[str]:
    countries = []
    for c in _as_list(activity.get("recipient-country")):
        if isinstance(c, dict) and c.get("@code"):
            countries.append(c.get("@code"))
    return countries


def _title(activity: dict) -> str:
    t_list = _as_list(activity.get("title"))
    return _narrative_text(t_list[0].get("narrative")) if t_list and isinstance(t_list[0], dict) else ""


def _descriptions(activity: dict) -> Tuple[str, str]:
    general = ""
    parts = []
    for d in _as_list(activity.get("description")):
        if not isinstance(d, dict):
            continue
        txt = _narrative_text(d.get("narrative"))
        if not txt:
            continue
        parts.append(txt)
        if not general and d.get("@type") in (None, "1"):
            general = txt
    if not general and parts:
        general = parts[0]
    return general, " ".join(parts)


def extract_equipment_targets(*texts: str) -> Tuple[str, str]:
    haystack = " ".join(t for t in texts if t)
    if not haystack:
        return "", ""
    categories_hit, snippets = [], []
    for category, patterns in _COMPILED_KEYWORDS.items():
        for pattern in patterns:
            m = pattern.search(haystack)
            if m:
                categories_hit.append(category)
                snippet = haystack[max(0, m.start() - 25): m.end() + 25].strip()
                snippets.append(f"{category}: …{snippet}…")
                break
    return "; ".join(categories_hit), " | ".join(snippets)


def parse_activity(raw_doc: dict) -> Optional[dict]:
    blob = raw_doc.get("iati_json", raw_doc)
    if isinstance(blob, str):
        try:
            blob = json.loads(blob)
        except json.JSONDecodeError:
            return None
    if not isinstance(blob, dict):
        return None
    activities = _as_list(blob.get("iati-activity"))
    if not activities:
        return None
    activity = activities[0]

    iati_id_list = _as_list(activity.get("iati-identifier"))
    iati_id = _text(iati_id_list[0]) if iati_id_list else ""
    if not iati_id:
        return None

    reporting_ref, reporting_name = _reporting_org(activity)
    funding_orgs = _participating_orgs_by_role(activity, ROLE_FUNDING)
    implementing_orgs = _participating_orgs_by_role(activity, ROLE_IMPLEMENTING)
    accountable_orgs = _participating_orgs_by_role(activity, ROLE_ACCOUNTABLE)

    status_list = _as_list(activity.get("activity-status"))
    status_code = status_list[0].get("@code", "") if status_list and isinstance(status_list[0], dict) else ""

    dates = _activity_dates(activity)
    budget_amount, budget_currency, n_budget_lines = _total_budget(activity)
    sectors = _sectors(activity)
    countries = _recipient_countries(activity)
    title = _title(activity)
    description, description_for_scan = _descriptions(activity)
    eq_categories, eq_snippets = extract_equipment_targets(title, description_for_scan)

    return {
        "iati_identifier": iati_id,
        "project_title": title,
        "reporting_org_ref": reporting_ref,
        "reporting_org_name": reporting_name,
        "funding_agencies": "; ".join(funding_orgs),
        "implementing_partners": "; ".join(implementing_orgs),
        "accountable_orgs": "; ".join(accountable_orgs),
        "country_codes": "; ".join(countries),
        "activity_status_code": status_code,
        "activity_status_label": ACTIVITY_STATUS_LABELS.get(status_code, status_code),
        "planned_start_date": dates.get(DATE_PLANNED_START, ""),
        "actual_start_date": dates.get(DATE_ACTUAL_START, ""),
        "planned_end_date": dates.get(DATE_PLANNED_END, ""),
        "actual_end_date": dates.get(DATE_ACTUAL_END, ""),
        "total_budget_amount": budget_amount,
        "budget_currency": budget_currency,
        "budget_line_count": n_budget_lines,
        "sector_codes": "; ".join(c for c, _ in sectors),
        "sector_names": "; ".join(n for _, n in sectors if n),
        "description": description,
        "equipment_target_summary": eq_categories,
        "equipment_target_snippets": eq_snippets,
    }

# =========================================================================
# FETCHING & QUERYING
# =========================================================================

def build_query(countries: List[str], sector_codes: List[str], status_codes: List[str]) -> str:
    country_clause = f"recipient_country_code:({' '.join(countries)})"
    sector_clause = f"sector_code:({' '.join(sector_codes)})"
    status_clause = f"activity_status_code:({' '.join(status_codes)})"
    return f"{country_clause} AND {sector_clause} AND {status_clause}"


def _session() -> requests.Session:
    retry = Retry(total=5, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def fetch_all_activities(
    query: str, api_key: str, rows_per_page: int, max_pages: int, sleep_seconds: float, dump_raw_path: Optional[str]
) -> List[dict]:
    session = _session()
    headers = {"Ocp-Apim-Subscription-Key": api_key}
    docs: List[dict] = []
    start, total_found, page = 0, None, 0

    while True:
        params = {"q": query, "fl": "iati_json", "wt": "json", "rows": rows_per_page, "start": start}
        resp = session.get(BASE_URL, headers=headers, params=params, timeout=60)
        if resp.status_code == 401:
            raise RuntimeError("401 Unauthorized: Verify IATI_API_KEY from https://developer.iatistandard.org")
        resp.raise_for_status()

        payload = resp.json()
        if page == 0 and dump_raw_path:
            with open(dump_raw_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)

        response_block = payload.get("response", {})
        if total_found is None:
            total_found = response_block.get("numFound", 0)
            print(f"[iati] API query matched {total_found} total activities")

        page_docs = response_block.get("docs", [])
        docs.extend(page_docs)

        page += 1
        start += rows_per_page
        if not page_docs or start >= total_found or page >= max_pages:
            break

        time.sleep(sleep_seconds)

    return docs

# =========================================================================
# DELTA ENGINE & WEBHOOK ALERTS
# =========================================================================

def process_deltas(df: pd.DataFrame, state_file: str, webhook_url: Optional[str]) -> None:
    state = {}
    if os.path.exists(state_file):
        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)

    alerts = []
    for _, row in df.iterrows():
        doc_id = row["iati_identifier"]
        title = row["project_title"]
        status = str(row["activity_status_code"])
        budget = float(row["total_budget_amount"] or 0.0)
        eq_tags = set(filter(None, (row["equipment_target_summary"] or "").split("; ")))

        is_new = doc_id not in state
        if is_new:
            alerts.append(f"🆕 *New Project Logged:* [{doc_id}] {title} (Budget: {budget:,.2f} {row['budget_currency']})")
        else:
            prev = state[doc_id]
            if prev.get("status") == "1" and status == "2":
                alerts.append(f"🚀 *Moved to Implementation:* [{doc_id}] {title}")
            if budget > prev.get("budget", 0.0):
                alerts.append(f"💰 *Budget Increased:* [{doc_id}] {title} (Now {budget:,.2f} {row['budget_currency']})")
            
            prev_tags = set(prev.get("equipment_tags", []))
            new_tags = eq_tags - prev_tags
            if new_tags:
                alerts.append(f"🩺 *New Procurement Focus:* [{doc_id}] {title} -> Targeted: {', '.join(new_tags)}")

        # Update in-memory state
        state[doc_id] = {
            "title": title,
            "status": status,
            "budget": budget,
            "equipment_tags": list(eq_tags),
            "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    # Save state
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    print(f"[iati] Saved tracking state ({len(state)} records) to {state_file}")

    # Dispatch alerts
    if alerts and webhook_url:
        print(f"[iati] Sending {len(alerts)} alerts to Webhook...")
        msg = "🚨 *IATI Health Equipment Tracker Alert*\n\n" + "\n".join(alerts[:15])
        if len(alerts) > 15:
            msg += f"\n\n...and {len(alerts) - 15} more updates."
        try:
            requests.post(webhook_url, json={"text": msg}, timeout=10)
        except Exception as e:
            print(f"[iati] Failed to send webhook alert: {e}", file=sys.stderr)

# =========================================================================
# ENTRY POINT
# =========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="IATI Health Project Extraction & Monitoring Pipeline")
    parser.add_argument("--api-key", default=os.environ.get("IATI_API_KEY"))
    parser.add_argument("--countries", nargs="+", default=TARGET_COUNTRIES)
    parser.add_argument("--statuses", nargs="+", default=TARGET_STATUS_CODES)
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--sleep", type=float, default=13.0)
    parser.add_argument("--output-prefix", default="iati_health_projects")
    parser.add_argument("--state-file", default="projects_state.json", help="Path to state file for delta tracking")
    parser.add_argument("--webhook-url", default=os.environ.get("SLACK_WEBHOOK_URL"))
    parser.add_argument("--dump-raw", metavar="PATH")
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    if args.mock:
        print("[iati] Running in --mock mode using built-in synthetic test record")
        raw_docs = [{
            "iati_json": {
                "iati-activity": [{
                    "iati-identifier": [{"text()": "XM-DAC-41114-KE-001"}],
                    "reporting-org": [{"narrative": [{"text()": "Global Fund"}]}],
                    "title": [{"narrative": [{"text()": "Western Kenya Hospital Cold Chain and ICU Diagnostic Upgrade"}]}],
                    "description": [{"narrative": [{"text()": "Procuring cold storage refrigerators, 4 ambulances, and diagnostic test kits."}]}],
                    "activity-status": [{"@code": "2"}],
                    "recipient-country": [{"@code": "KE"}],
                    "sector": [{"@code": "12230"}],
                    "budget": [{"value": [{"@currency": "USD", "text()": "1500000"}]}]
                }]
            }
        }]
    else:
        if not args.api_key:
            print("[iati] ERROR: Missing API key. Pass --api-key or set IATI_API_KEY.", file=sys.stderr)
            sys.exit(1)
        query = build_query(args.countries, list(SECTOR_CODES.keys()), args.statuses)
        raw_docs = fetch_all_activities(query, args.api_key, args.rows, args.max_pages, args.sleep, args.dump_raw)

    records = [parse_activity(doc) for doc in raw_docs]
    records = [r for r in records if r]

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.drop_duplicates(subset=["iati_identifier"]).reset_index(drop=True)

    print(f"[iati] Successfully parsed {len(df)} activities.")
    
    csv_path = f"{args.output_prefix}.csv"
    json_path = f"{args.output_prefix}.json"
    df.to_csv(csv_path, index=False)
    df.to_json(json_path, orient="records", indent=2, force_ascii=False)
    print(f"[iati] Datasets saved to {csv_path} and {json_path}")

    # Process deltas and dispatch alerts if tracking state is active
    process_deltas(df, args.state_file, args.webhook_url)


if __name__ == "__main__":
    main()
