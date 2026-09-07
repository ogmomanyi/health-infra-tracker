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
ACTIVE_STAGES = ("invitation for bids", "request for bids", "request for proposals", "request for quotation", "request for expression of interest", "expression of interest", "invitation to bid", "call for proposals", "rfq", "rfb", "rfp", "ifb")
FARAM_KEYWORDS = ("laboratory", "lab equipment", "analyzer", "analys", "hematology", "haematology", "diagnostic", "test kit", "reagent", "molecular", "pcr", "genexpert", "gene xpert", "medical equipment", "medical device", "patient monitor", "ventilator", "ultrasound", "blood bank", "blood banking", "apheresis", "cold chain", "vaccine refrigerator", "sterilizer", "sterilisation", "sterilization", "autoclave", "ophthalm", "slit lamp", "tonometer", "fundus", "ppe", "surgical glove", "examination glove", "face mask", "pipette", "specimen collection", "laboratory consumable", "lab consumable")


def load_projects(path: Path, database: Path | None = None) -> list[dict]:
    if path.exists():
        with path.open(newline="", encoding="utf-8") as handle:
            projects = list(csv.DictReader(handle))
        if projects:
            return projects
    return load_iati_candidates(database) if database is not None else []


def _date(value: str) -> date | None:
    try:
        return date.fromisoformat((value or "").strip())
    except (TypeError, ValueError):
        return None


def classify_opportunity_status(event: ProcurementEvent, today: date | None = None) -> str:
    today = today or date.today()
    stage = (event.procurement_stage or "").strip().lower()
    combined = f"{stage} {(event.title or '').strip().lower()}"
    if "contract award" in combined or "award notice" in combined or stage == "award": return "AWARD_HISTORY"
    if "procurement plan" in combined or "potential procurement" in combined: return "PROCUREMENT_PLAN"
    if "general procurement notice" in combined or "general procurement" in combined or "gpn" in stage: return "UPCOMING_GPN"
    closing = _date(event.closing_date)
    if closing:
        if closing >= today and any(token in combined for token in ACTIVE_STAGES): return "ACTIVE_OPPORTUNITY"
        if closing < today: return "CLOSED_OPPORTUNITY"
    return "NOTICE" if any(token in combined for token in ACTIVE_STAGES) else "UNKNOWN"


def score_faram_relevance(event: ProcurementEvent) -> tuple[float, str, str]:
    text = " ".join((event.title, event.equipment_category, event.product_family, event.procurement_stage)).lower()
    score = 0.0; reasons: list[str] = []
    categories = {"Laboratory Equipment", "Diagnostics", "Medical Equipment", "Blood Banking", "Cold Chain", "Sterilization", "PPE", "Ophthalmology", "Laboratory Consumables"}
    if event.equipment_category in categories: score += 35; reasons.append(event.equipment_category.lower())
    if event.country.strip().lower() in {c.lower() for c in FARAM_COUNTRIES}: score += 15; reasons.append(event.country.strip())
    hits = {k for k in FARAM_KEYWORDS if k in text}
    if hits: score += min(15, 5 * len(hits))
    status = classify_opportunity_status(event)
    if status == "ACTIVE_OPPORTUNITY": score += 25; reasons.append("active bid")
    elif status == "UPCOMING_GPN": score += 12; reasons.append("upcoming procurement")
    elif status == "PROCUREMENT_PLAN": score += 10; reasons.append("procurement plan")
    elif status == "AWARD_HISTORY": score += 5; reasons.append("award/history")
    if event.match_status == "CONFIRMED": score += 10; reasons.append("confirmed IATI project link")
    elif event.match_status == "POSSIBLE": score += 5; reasons.append("possible IATI project link")
    score = min(100.0, round(score, 1))
    priority = "HIGH" if score >= 70 else "MEDIUM" if score >= 45 else "LOW" if score > 0 else "MONITOR"
    reason = "; ".join(reasons).capitalize() + "." if reasons else "No strong Faram product or market fit identified by the heuristic."
    return score, priority, reason


def resolve_supplier_entities(events: list[ProcurementEvent], database: Path) -> list[ProcurementEvent]:
    """Attach deterministic supplier entity IDs to explicit award records."""
    import sqlite3
    from .supplier_resolution import ensure_supplier_registry, load_supplier_candidates, resolve_supplier, seed_explicit_suppliers

    conn = sqlite3.connect(database)
    try:
        ensure_supplier_registry(conn)
        explicit = [
            (event.supplier_name, event.supplier_country)
            for event in events
            if event.supplier_evidence_status == "EXPLICIT" and event.supplier_name.strip()
        ]
        seed_explicit_suppliers(conn, explicit)
        candidates = load_supplier_candidates(conn)
        resolved = []
        for event in events:
            if event.supplier_evidence_status != "EXPLICIT" or not event.supplier_name.strip():
                resolved.append(event)
                continue
            result = resolve_supplier(event.supplier_name, event.supplier_country, candidates)
            resolved.append(ProcurementEvent(**{
                **event.to_dict(),
                "supplier_entity_id": result.entity_id or "",
                "supplier_canonical_name": result.canonical_name or "",
                "supplier_match_status": result.match_method,
                "supplier_match_confidence": result.confidence_score,
            }))
        return resolved
    finally:
        conn.close()


def build_events(notices, projects):
    matched = []
    fields = ProcurementEvent.__dataclass_fields__
    for notice in notices:
        event = ProcurementEvent(**{field: notice.get(field, "") for field in fields})
        result = match_event(event, projects)
        enriched = ProcurementEvent(**{**event.to_dict(), "matched_iati_identifier": result["matched_iati_identifier"], "match_confidence": result["match_confidence"], "match_status": result["match_status"]})
        status = classify_opportunity_status(enriched); score, priority, reason = score_faram_relevance(enriched)
        matched.append(ProcurementEvent(**{**enriched.to_dict(), "opportunity_status": status, "faram_relevance_score": score, "faram_relevance_reason": reason, "procurement_priority": priority}))
    return matched


def _warn(source: str, exc: Exception) -> None: print(f"WARNING: {source} procurement source failed: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/procurement_events_input.csv"); parser.add_argument("--output", default="data/procurement_events.csv"); parser.add_argument("--projects", default="data/opportunities.csv"); parser.add_argument("--database", default="data/iati_intelligence.db"); parser.add_argument("--buyer-output", default="data/procurement_buyer_history.csv"); parser.add_argument("--supplier-output", default="data/procurement_supplier_history.csv")
    parser.add_argument("--source", choices=["fixture", "world_bank", "rss", "afdb", "undp", "all"], default="fixture"); parser.add_argument("--country", action="append", dest="countries"); parser.add_argument("--feed-url"); parser.add_argument("--feed-name", default="Official RSS"); parser.add_argument("--page-url", action="append", dest="page_urls"); parser.add_argument("--afdb-feed-url"); parser.add_argument("--afdb-page-url", action="append", dest="afdb_page_urls"); parser.add_argument("--undp-url", default="https://procurement-notices.undp.org/")
    args = parser.parse_args(); notices = []; source_successes = 0
    if args.source in {"world_bank", "all"}:
        from .sources.world_bank import fetch_notices, normalize_notices
        try:
            codes = args.countries or [None]
            for code in codes: notices.extend(normalize_notices(fetch_notices(country_codes=[code] if code else None)))
            source_successes += 1
        except Exception as exc:
            if args.source == "world_bank": raise
            _warn("World Bank", exc)
    if args.source == "rss":
        if not args.feed_url: parser.error("--feed-url is required when --source=rss")
        from .sources.rss import fetch_feed, normalize_notices
        notices = normalize_notices(fetch_feed(args.feed_url), source=args.feed_name); source_successes += 1
    elif args.source == "afdb":
        if args.feed_url:
            from .sources.rss import fetch_feed, normalize_notices; notices = normalize_notices(fetch_feed(args.feed_url), source="AfDB")
        elif args.page_urls:
            from .sources.afdb import fetch_page, parse_notice_page
            for url in args.page_urls: notices.extend(parse_notice_page(fetch_page(url), url))
        else: parser.error("--feed-url or --page-url is required when --source=afdb")
        source_successes += 1
    elif args.source == "undp":
        from .sources.undp import fetch_page, parse_notice_page; notices = parse_notice_page(fetch_page(args.undp_url), args.undp_url); source_successes += 1
    elif args.source == "all":
        if args.afdb_feed_url:
            from .sources.rss import fetch_feed, normalize_notices
            try: notices.extend(normalize_notices(fetch_feed(args.afdb_feed_url), source="AfDB")); source_successes += 1
            except Exception as exc: _warn("AfDB feed", exc)
        if args.afdb_page_urls:
            from .sources.afdb import fetch_page, parse_notice_page; ok = False
            for url in args.afdb_page_urls:
                try: notices.extend(parse_notice_page(fetch_page(url), url)); ok = True
                except Exception as exc: _warn(f"AfDB page {url}", exc)
            if ok: source_successes += 1
        from .sources.undp import fetch_page, parse_notice_page
        try: notices.extend(parse_notice_page(fetch_page(args.undp_url), args.undp_url)); source_successes += 1
        except Exception as exc: _warn("UNDP", exc)
    elif args.source == "fixture": notices = [event.to_dict() for event in read_events(Path(args.input))]; source_successes = 1
    if not notices and args.source == "all" and source_successes == 0: raise RuntimeError("All external procurement sources failed; refusing to overwrite the existing dataset.")
    projects = load_projects(Path(args.projects), Path(args.database)); print(f"IATI matching candidates loaded: {len(projects)}")
    fresh_events = resolve_supplier_entities(build_events(notices, projects), Path(args.database))
    events = merge_events([e for e in load_events(Path(args.output)) if not e.procurement_event_id.startswith("proc_demo_")], fresh_events) if args.source == "all" else fresh_events
    write_events(Path(args.output), events); persist_events(Path(args.database), events)
    from .commercial import write_buyer_history
    buyer_count = write_buyer_history(Path(args.buyer_output), events, database=Path(args.database))
    from .supplier_intelligence import write_supplier_history
    supplier_count = write_supplier_history(Path(args.supplier_output), events)
    matched = sum(e.match_status in {"POSSIBLE", "CONFIRMED"} for e in events); confirmed = sum(e.match_status == "CONFIRMED" for e in events)
    resolved_suppliers = sum(bool(e.supplier_entity_id) for e in events)
    print(f"Procurement intelligence pipeline completed: {len(events)} events, {matched} matched, {confirmed} confirmed")
    print(f"Buyer intelligence generated: {buyer_count} buyer accounts")
    print(f"Supplier intelligence generated: {supplier_count} explicit supplier accounts; {resolved_suppliers} awards entity-resolved")

if __name__ == "__main__": main()
