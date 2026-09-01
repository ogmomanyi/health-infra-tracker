#!/usr/bin/env python3
"""Run normalized external procurement intelligence against IATI opportunities."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from .clients.ungm import UNGMClient
from .ingest import read_events, write_events
from .matcher import match_event
from .pipeline import persist_events
from .schema import ProcurementEvent
from .sources.ungm import normalize_notices


def load_projects(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def build_events(notices, projects):
    events = normalize_notices(notices)
    matched = []
    for event in events:
        result = match_event(event, projects)
        matched.append(
            ProcurementEvent(
                **{
                    **event.to_dict(),
                    "matched_iati_identifier": result["matched_iati_identifier"],
                    "match_confidence": result["match_confidence"],
                    "match_status": result["match_status"],
                }
            )
        )
    return matched


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/procurement_events_input.csv")
    parser.add_argument("--output", default="data/procurement_events.csv")
    parser.add_argument("--projects", default="data/opportunities.csv")
    parser.add_argument("--database", default="data/iati_intelligence.db")
    parser.add_argument(
        "--source",
        choices=["fixture", "ungm"],
        default="fixture",
        help="Read notices from a local fixture or the authenticated UNGM Notice API.",
    )
    parser.add_argument("--page-size", type=int, default=None)
    args = parser.parse_args()

    if args.source == "ungm":
        params = {"$top": args.page_size} if args.page_size else None
        notices = UNGMClient().get_notices(params=params)
    else:
        source_events = list(read_events(Path(args.input)))
        notices = [event.to_dict() for event in source_events]

    projects = load_projects(Path(args.projects))
    events = build_events(notices, projects)
    write_events(Path(args.output), events)
    persist_events(Path(args.database), events)

    matched = sum(event.match_status in {"POSSIBLE", "CONFIRMED"} for event in events)
    confirmed = sum(event.match_status == "CONFIRMED" for event in events)
    print(
        "Procurement intelligence pipeline completed: "
        f"{len(events)} events, {matched} matched, {confirmed} confirmed"
    )


if __name__ == "__main__":
    main()
