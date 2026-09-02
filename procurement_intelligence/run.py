#!/usr/bin/env python3
"""Run external procurement intelligence against IATI opportunities."""

from __future__ import annotations
import argparse
import csv
from pathlib import Path
from .ingest import read_events, write_events
from .matcher import match_event
from .pipeline import load_events, merge_events, persist_events
from .schema import ProcurementEvent


def load_projects(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def build_events(notices, projects):
    matched = []
    fields = ProcurementEvent.__dataclass_fields__
    for notice in notices:
        event = ProcurementEvent(**{field: notice.get(field, "") for field in fields})
        result = match_event(event, projects)
        matched.append(ProcurementEvent(**{**event.to_dict(), **{
            "matched_iati_identifier": result["matched_iati_identifier"],
            "match_confidence": result["match_confidence"],
            "match_status": result["match_status"],
        }}))
    return matched


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
    if args.source in {"world_bank", "all"}:
        from .sources.world_bank import fetch_notices, normalize_notices
        notices.extend(normalize_notices(fetch_notices(country_codes=args.countries)))

    if args.source == "rss":
        if not args.feed_url:
            parser.error("--feed-url is required when --source=rss")
        from .sources.rss import fetch_feed, normalize_notices
        notices = normalize_notices(fetch_feed(args.feed_url), source=args.feed_name)
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
    elif args.source == "undp":
        from .sources.undp import fetch_page, parse_notice_page
        notices = parse_notice_page(fetch_page(args.undp_url), args.undp_url)
    elif args.source == "all":
        if args.afdb_feed_url:
            from .sources.rss import fetch_feed, normalize_notices
            notices.extend(normalize_notices(fetch_feed(args.afdb_feed_url), source="AfDB"))
        if args.afdb_page_urls:
            from .sources.afdb import fetch_page, parse_notice_page
            for page_url in args.afdb_page_urls:
                notices.extend(parse_notice_page(fetch_page(page_url), page_url))
        from .sources.undp import fetch_page, parse_notice_page
        notices.extend(parse_notice_page(fetch_page(args.undp_url), args.undp_url))
    elif args.source == "fixture":
        notices = [event.to_dict() for event in read_events(Path(args.input))]

    fresh_events = build_events(notices, load_projects(Path(args.projects)))
    if args.source == "all":
        events = merge_events(load_events(Path(args.output)), fresh_events)
    else:
        events = fresh_events

    write_events(Path(args.output), events)
    persist_events(Path(args.database), events)
    matched = sum(event.match_status in {"POSSIBLE", "CONFIRMED"} for event in events)
    confirmed = sum(event.match_status == "CONFIRMED" for event in events)
    print(f"Procurement intelligence pipeline completed: {len(events)} events, {matched} matched, {confirmed} confirmed")


if __name__ == "__main__":
    main()
