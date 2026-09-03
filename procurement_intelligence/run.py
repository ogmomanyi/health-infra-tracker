#!/usr/bin/env python3
"""Run external procurement intelligence against normalized IATI activities."""

from __future__ import annotations
import argparse
import csv
from datetime import date
from pathlib import Path
from .ingest import read_events, write_events
from .matcher import match_event
from .pipeline import load_events, merge_events, persist_events
from .schema import ProcurementEvent
from .iati_candidates import load_iati_candidates

FARAM_COUNTRIES = {"Kenya", "Uganda", "Rwanda", "Ethiopia", "Somalia", "South Sudan", "Congo, Democratic Republic of the"}
ACTIVE_STAGES = (
    "invitation for bids", "request for bids", "request for proposals",
    "request for quotation", "request for expression of interest",
    "expression of interest", "invitation to bid", "call for proposals",
    "rfq", "rfb", "rfp", "ifb",
)
FARAM_KEYWORDS = (
    "laboratory", "lab equipment", "analyzer", "analys", "hematology", "haematology",
    "diagnostic", "test kit", "reagent", "molecular", "pcr", "genexpert", "gene xpert",
    "medical equipment", "medical device", "patient monitor", "ventilator", "ultrasound",
    "blood bank", "blood banking", "apheresis", "cold chain", "vaccine refrigerator",
    "sterilizer", "sterilisation", "sterilization", "autoclave", "ophthalm", "slit lamp",
    "tonometer", "fundus", "ppe", "surgical glove", "examination glove", "face mask",
    "pipette", "specimen collection", "laboratory consumable", "lab consumable",
)


def load_projects(path: Path, database: Path | None = None) -> list[dict]:
    """Load an explicit project CSV, falling back to normalized IATI activities."""
    if path.exists():
        with path.open(newline="", encoding="utf-8") as handle:
            projects = list(csv.DictReader(handle))
        if projects:
            return projects
    if database is not None:
        return load_iati_candidates(database)
    return []


def _date(value: str) -> date | None:
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def classify_opportunity_status(event: ProcurementEvent, today: date | None = None) -> str:
    """Classify a notice by actionability while retaining awards/history."""
    today = today or date.today()
    stage = (event.procurement_stage or "").strip().lower()
    title = (event.title or "").strip().lower()
    combined = f"{stage} {title}"

    if "contract award" in combined or "award notice" in combined or stage == "award":
        return "AWARD_HISTORY"
    if "procurement plan" in combined or "potential procurement" in combined:
        return "PROCUREMENT_PLAN"
    if "general procurement notice" in combined or "general procurement" in combined or "gpn" in stage:
        return "UPCOMING_GPN"

    closing = _date(event.closing_date)
    if closing:
        if closing >= today and any(token in combined for token in ACTIVE_STAGES):
            return "ACTIVE_OPPORTUNITY"
        if closing < today:
            return "CLOSED_OPPORTUNITY"

    if any(token in combined for token in ACTIVE_STAGES):
        return "NOTICE"
    return "UNKNOWN"


def score_faram_relevance(event: ProcurementEvent) -> tuple[float, str, str]:
    """Return a transparent heuristic score, priority, and human-readable reason."""
    text = " ".join((event.title, event.equipment_category, event.product_family, event.procurement_stage)).lower()
    score = 0.0
    reasons: list[str] = []

    category_fit = {
        "Laboratory Equipment", "Diagnostics", "Medical Equipment", "Blood Banking",
        "Cold Chain", "Sterilization", "PPE", "Ophthalmology", "Laboratory Consumables",
    }
    if event.equipment_category in category_fit:
        score += 35
        reasons.append(event.equipment_category.lower())
    if event.country.strip().lower() in {country.lower() for country in FARAM_COUNTRIES}:
        score += 15
        reasons.append(event.country.strip() or "priority market")

    keyword_hits = [keyword for keyword in FARAM_KEYWORDS if keyword in text]
    if keyword_hits:
        score += min(15, 5 * len(set(keyword_hits)))

    status = classify_opportunity_status(event)
    if status == "ACTIVE_OPPORTUNITY":
        score += 25
        reasons.append("active bid")
    elif status == "UPCOMING_GPN":
        score += 12
        reasons.append("upcoming procurement")
    elif status == "PROCUREMENT_PLAN":
        score += 10
        reasons.append("procurement plan")
    elif status == "AWARD_HISTORY":
        score += 5
        reasons.append("award/history")

    if event.match_status == "CONFIRMED":
        score += 10
        reasons.append("confirmed IATI project link")
    elif event.match_status == "POSSIBLE":
        score += 5
        reasons.append("possible IATI project link")

    score = min(100.0, round(score, 1))
    if score >= 70:
        priority = "HIGH"
    elif score >= 45:
        priority = "MEDIUM"
    elif score > 0:
        priority = "LOW"
    else:
        priority = "MONITOR"

    if reasons:
        reason = "; ".join(reasons)
        reason = reason[0].upper() + reason[1:] + "."
    else:
        reason = "No strong Faram product or market fit identified by the heuristic."
    return score, priority, reason


def build_events(notices, projects):
    matched = []
    fields = ProcurementEvent.__dataclass_fields__
    for notice in notices:
        event = ProcurementEvent(**{field: notice.get(field, "") for field in fields})
        result = match_event(event, projects)
        enriched = ProcurementEvent(**{**event.to_dict(), **{
            "matched_iati_identifier": result["matched_iati_identifier"],
            "match_confidence": result["match_confidence"],
            "match_status": result["match_status"],
        }})
        status = classify_opportunity_status(enriched)
        score, priority, reason = score_faram_relevance(enriched)
        matched.append(ProcurementEvent(**{**enriched.to_dict(), **{
            "opportunity_status": status,
            "faram_relevance_score": score,
            "faram_relevance_reason": reason,
            "procurement_priority": priority,
        }}))
    return matched


def _warn(source: str, exc: Exception) -> None:
    print(f"WARNING: {source} procurement source failed: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/procurement_events_input.csv")
    parser.add_argument("--output", default="data/procurement_events.csv")
    parser.add_argument("--projects", default="data/opportunities.csv")
    parser.add_argument("--database", default="data/iati_intelligence.db")
    parser.add_argument("--source", choices=["fixture", "world_bank", "rss", "afdb", "undp", "all"], default="fixture")
    parser.add_argument("--country", action="append", dest="countries", help="World Bank ISO country code; repeatable.")
    parser.add_argument("--feed-url", help="Official RSS/Atom feed URL when --source=rss or --source=afdb.")
    parser.add_argument("--feed-name", default="Official RSS", help="Publisher name for an RSS source.")
    parser.add_argument("--page-url", action="append", dest="page_urls", help="Official AfDB procurement notice page; repeatable when --source=afdb.")
    parser.add_argument("--afdb-feed-url", help="Official AfDB RSS/Atom feed URL when --source=all.")
    parser.add_argument("--afdb-page-url", action="append", dest="afdb_page_urls", help="Official AfDB procurement page when --source=all; repeatable.")
    parser.add_argument("--undp-url", default="https://procurement-notices.undp.org/", help="Public UNDP procurement notice listing URL when --source=undp or --source=all.")
    args = parser.parse_args()

    notices = []
    source_successes = 0

    if args.source in {"world_bank", "all"}:
        from .sources.world_bank import fetch_notices, normalize_notices
        try:
            if args.countries:
                for country_code in args.countries:
                    notices.extend(normalize_notices(fetch_notices(country_codes=[country_code])))
            else:
                notices.extend(normalize_notices(fetch_notices()))
            source_successes += 1
        except Exception as exc:
            if args.source == "world_bank":
                raise
            _warn("World Bank", exc)

    if args.source == "rss":
        if not args.feed_url:
            parser.error("--feed-url is required when --source=rss")
        from .sources.rss import fetch_feed, normalize_notices
        notices = normalize_notices(fetch_feed(args.feed_url), source=args.feed_name)
        source_successes += 1
    elif args.source == "afdb":
        if args.feed_url:
            from .sources.rss import fetch_feed, normalize_notices
            notices = normalize_notices(fetch_feed(args.feed_url), source="AfDB")
        elif args.page_urls:
            from .sources.afdb import fetch_page, parse_notice_page
            for page_url in args.page_urls:
                notices.extend(parse_notice_page(fetch_page(page_url), page_url))
        else:
            parser.error("--feed-url or --page-url is required when --source=afdb")
        source_successes += 1
    elif args.source == "undp":
        from .sources.undp import fetch_page, parse_notice_page
        notices = parse_notice_page(fetch_page(args.undp_url), args.undp_url)
        source_successes += 1
    elif args.source == "all":
        if args.afdb_feed_url:
            from .sources.rss import fetch_feed, normalize_notices
            try:
                notices.extend(normalize_notices(fetch_feed(args.afdb_feed_url), source="AfDB"))
                source_successes += 1
            except Exception as exc:
                _warn("AfDB feed", exc)
        if args.afdb_page_urls:
            from .sources.afdb import fetch_page, parse_notice_page
            afdb_page_success = False
            for page_url in args.afdb_page_urls:
                try:
                    notices.extend(parse_notice_page(fetch_page(page_url), page_url))
                    afdb_page_success = True
                except Exception as exc:
                    _warn(f"AfDB page {page_url}", exc)
            if afdb_page_success:
                source_successes += 1
        from .sources.undp import fetch_page, parse_notice_page
        try:
            notices.extend(parse_notice_page(fetch_page(args.undp_url), args.undp_url))
            source_successes += 1
        except Exception as exc:
            _warn("UNDP", exc)
    elif args.source == "fixture":
        notices = [event.to_dict() for event in read_events(Path(args.input))]
        source_successes = 1

    if not notices and args.source == "all" and source_successes == 0:
        raise RuntimeError("All external procurement sources failed; refusing to overwrite the existing dataset.")

    projects = load_projects(Path(args.projects), Path(args.database))
    print(f"IATI matching candidates loaded: {len(projects)}")
    fresh_events = build_events(notices, projects)
    if args.source == "all":
        existing_events = [
            event for event in load_events(Path(args.output))
            if not event.procurement_event_id.startswith("proc_demo_")
        ]
        events = merge_events(existing_events, fresh_events)
    else:
        events = fresh_events

    write_events(Path(args.output), events)
    persist_events(Path(args.database), events)
    matched = sum(event.match_status in {"POSSIBLE", "CONFIRMED"} for event in events)
    confirmed = sum(event.match_status == "CONFIRMED" for event in events)
    print(f"Procurement intelligence pipeline completed: {len(events)} events, {matched} matched, {confirmed} confirmed")


if __name__ == "__main__":
    main()
