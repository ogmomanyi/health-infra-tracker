"""Build event-level commercial work items from the canonical action queue.

This is an execution bridge, not a second scoring layer. Account priority and
recommended actions remain authoritative; this module only fans actionable
procurement event IDs into CRM-ready opportunity rows and retains account-level
rows when no procurement event is available.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path

FIELDS = [
    "opportunity_id",
    "action_id",
    "target_account_id",
    "account_name",
    "country",
    "account_type",
    "crm_stage",
    "commercial_account_priority_score",
    "commercial_account_priority_tier",
    "action_category",
    "action_status",
    "assigned_owner",
    "next_activity",
    "next_activity_due_date",
    "procurement_event_id",
    "tender_reference",
    "title",
    "buyer",
    "procurement_stage",
    "publication_date",
    "closing_date",
    "days_to_closing",
    "estimated_value",
    "currency",
    "equipment_category",
    "product_family",
    "catalogue_fit_status",
    "catalogue_matched_products",
    "source",
    "source_url",
    "priority_reason",
    "recommended_action",
    "familiarity_evidence_ids",
]


def text(value: object) -> str:
    return " ".join(str(value or "").split())


def number(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def parse_date(value: object) -> date | None:
    try:
        return date.fromisoformat(text(value))
    except (TypeError, ValueError):
        return None


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def split_ids(value: object) -> list[str]:
    return [item.strip() for item in text(value).split(";") if item.strip()]


def event_index(events: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {
        text(row.get("procurement_event_id")): row
        for row in events
        if text(row.get("procurement_event_id"))
    }


def activity(row: dict[str, str], has_event: bool) -> str:
    category = text(row.get("action_category"))
    if has_event:
        return {
            "QUALIFY_AND_BID": "Qualify tender and confirm bid/no-bid",
            "RESOLVE_PRODUCT_OR_TERRITORY_FIT": "Resolve product and territory fit",
            "BID_PREPARATION": "Prepare bid and confirm requirements",
            "ACCOUNT_DEVELOPMENT": "Engage account and map procurement stakeholders",
        }.get(category, "Review procurement opportunity")
    return {
        "PIPELINE_DEVELOPMENT": "Develop account pipeline and map procurement stakeholders",
        "ACCOUNT_DEVELOPMENT": "Engage account and map procurement stakeholders",
    }.get(category, text(row.get("recommended_action")) or "Review account action")


def build_opportunity_workspace(
    actions: list[dict[str, str]],
    events: list[dict[str, str]],
    today: date | None = None,
) -> list[dict[str, str]]:
    today = today or date.today()
    by_id = event_index(events)
    output: list[dict[str, str]] = []
    seen: set[str] = set()

    for action in actions:
        event_ids = split_ids(action.get("procurement_event_ids"))
        matched_events = [by_id[event_id] for event_id in event_ids if event_id in by_id]

        # If the queue references events that are not present in the current
        # snapshot, retain one account-level work item rather than inventing data.
        rows = matched_events or [None]
        for event in rows:
            event_id = text(event.get("procurement_event_id")) if event else ""
            opportunity_id = "OPP-" + event_id if event_id else "OPP-" + text(action.get("action_id"))
            if opportunity_id in seen:
                continue
            seen.add(opportunity_id)

            closing = parse_date(event.get("closing_date")) if event else parse_date(action.get("next_closing_date"))
            days = ""
            if closing:
                days = str((closing - today).days)

            due_date = text(action.get("action_due_date"))
            output.append({
                "opportunity_id": opportunity_id,
                "action_id": text(action.get("action_id")),
                "target_account_id": text(action.get("target_account_id")),
                "account_name": text(action.get("account_name")),
                "country": text(action.get("country")),
                "account_type": text(action.get("account_type")),
                "crm_stage": text(action.get("crm_stage")),
                "commercial_account_priority_score": text(action.get("commercial_account_priority_score")),
                "commercial_account_priority_tier": text(action.get("commercial_account_priority_tier")),
                "action_category": text(action.get("action_category")),
                "action_status": text(action.get("action_status")),
                "assigned_owner": text(action.get("assigned_owner")),
                "next_activity": activity(action, bool(event)),
                "next_activity_due_date": due_date,
                "procurement_event_id": event_id,
                "tender_reference": text(event.get("tender_reference")) if event else "",
                "title": text(event.get("title")) if event else "",
                "buyer": text(event.get("buyer")) if event else text(action.get("account_name")),
                "procurement_stage": text(event.get("procurement_stage")) if event else "",
                "publication_date": text(event.get("publication_date")) if event else "",
                "closing_date": text(event.get("closing_date")) if event else text(action.get("next_closing_date")),
                "days_to_closing": days,
                "estimated_value": text(event.get("estimated_value")) if event else text(action.get("estimated_opportunity_value")),
                "currency": text(event.get("currency")) if event else "",
                "equipment_category": text(event.get("equipment_category")) if event else "",
                "product_family": text(event.get("product_family")) if event else "",
                "catalogue_fit_status": text(action.get("catalogue_fit_status")),
                "catalogue_matched_products": text(action.get("catalogue_matched_products")),
                "source": text(event.get("source")) if event else "",
                "source_url": text(event.get("source_url")) if event else "",
                "priority_reason": text(action.get("priority_reason")),
                "recommended_action": text(action.get("recommended_action")),
                "familiarity_evidence_ids": text(action.get("familiarity_evidence_ids")),
            })

    return sorted(
        output,
        key=lambda row: (
            -number(row["commercial_account_priority_score"]),
            parse_date(row["closing_date"]) or date.max,
            text(row["account_name"]).lower(),
            text(row["opportunity_id"]),
        ),
    )


def write_workspace(output_path: Path, action_path: Path, events_path: Path, today: date | None = None) -> int:
    rows = build_opportunity_workspace(load_csv(action_path), load_csv(events_path), today=today)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--actions", default="data/commercial_action_queue.csv")
    parser.add_argument("--events", default="data/procurement_events.csv")
    parser.add_argument("--output", default="data/commercial_opportunity_workspace.csv")
    args = parser.parse_args()
    count = write_workspace(Path(args.output), Path(args.actions), Path(args.events))
    print(f"Commercial opportunity workspace completed: {count} opportunities")


if __name__ == "__main__":
    main()
