#!/usr/bin/env python3
"""Run the normalized external procurement intelligence pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path

from .ingest import write_events
from .matcher import match_event
from .pipeline import persist_events
from .schema import ProcurementEvent
from .sources.ungm import normalize_notices


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
    parser.add_argument("--database", default="data/iati_intelligence.db")
    args = parser.parse_args()

    # The source adapter intentionally consumes extracted notice dictionaries.
    # This keeps network retrieval outside the canonical normalization layer.
    from .ingest import read_events

    source_events = list(read_events(Path(args.input)))
    notices = [event.to_dict() for event in source_events]

    # When called as a fixture/integration runner, no project file is required.
    # A future IATI integration can supply the live project dictionaries here.
    projects = []
    events = build_events(notices, projects)
    write_events(Path(args.output), events)
    persist_events(Path(args.database), events)
    print(f"Procurement intelligence pipeline completed: {len(events)} events")


if __name__ == "__main__":
    main()
