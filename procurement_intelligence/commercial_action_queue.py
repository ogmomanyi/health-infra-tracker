"""Turn canonical commercial account priority into an execution work queue."""
from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path

FIELDS = [
    "action_id",
    "target_account_id",
    "account_name",
    "country",
    "account_type",
    "crm_stage",
    "commercial_account_priority_score",
    "commercial_account_priority_tier",
    "action_category",
    "recommended_action",
    "action_status",
    "assigned_owner",
    "action_due_date",
    "days_to_closing",
    "next_closing_date",
    "active_opportunities",
    "high_priority_opportunities",
    "upcoming_pipeline",
    "estimated_opportunity_value",
    "catalogue_fit_status",
    "catalogue_matched_events",
    "catalogue_matched_products",
    "procurement_event_ids",
    "familiarity_evidence_ids",
    "priority_reason",
]

ACTIONABLE_TIERS = {"ACT_NOW", "PRIORITISE", "DEVELOP"}


def text(value: object) -> str:
    return " ".join(str(value or "").split())


def number(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def integer(value: object) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


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


def action_category(row: dict[str, str]) -> str:
    tier = text(row.get("commercial_account_priority_tier")).upper()
    fit = text(row.get("catalogue_fit_status")).upper()
    active = integer(row.get("active_opportunities"))
    familiarity = number(row.get("historical_familiarity_score"))

    if tier == "ACT_NOW" and fit == "FARAM_MATCH" and active:
        return "QUALIFY_AND_BID"
    if tier == "ACT_NOW" and fit != "FARAM_MATCH":
        return "RESOLVE_PRODUCT_OR_TERRITORY_FIT"
    if tier == "PRIORITISE" and fit == "FARAM_MATCH" and active:
        return "BID_PREPARATION"
    if tier == "PRIORITISE" and familiarity > 0:
        return "ACCOUNT_DEVELOPMENT"
    if tier == "DEVELOP":
        return "PIPELINE_DEVELOPMENT"
    return "WATCHLIST"


def build_action_queue(rows: list[dict[str, str]], today: date | None = None) -> list[dict[str, str]]:
    today = today or date.today()
    output: list[dict[str, str]] = []

    for row in rows:
        tier = text(row.get("commercial_account_priority_tier")).upper()
        if tier not in ACTIONABLE_TIERS:
            continue

        closing = parse_date(row.get("next_closing_date"))
        days_to_closing = ""
        due_date = ""
        if closing:
            days = (closing - today).days
            days_to_closing = str(days)
            if days >= 0:
                due_date = closing.isoformat()

        event_ids = [item.strip() for item in text(row.get("procurement_event_ids")).split(";") if item.strip()]
        action_id = "ACTION-" + (event_ids[0] if event_ids else text(row.get("target_account_id")))

        output.append(
            {
                "action_id": action_id,
                "target_account_id": text(row.get("target_account_id")),
                "account_name": text(row.get("account_name")),
                "country": text(row.get("country")),
                "account_type": text(row.get("account_type")),
                "crm_stage": text(row.get("crm_stage")),
                "commercial_account_priority_score": text(row.get("commercial_account_priority_score")),
                "commercial_account_priority_tier": tier,
                "action_category": action_category(row),
                "recommended_action": text(row.get("recommended_action")),
                "action_status": "OPEN",
                "assigned_owner": "",
                "action_due_date": due_date,
                "days_to_closing": days_to_closing,
                "next_closing_date": text(row.get("next_closing_date")),
                "active_opportunities": text(row.get("active_opportunities")),
                "high_priority_opportunities": text(row.get("high_priority_opportunities")),
                "upcoming_pipeline": text(row.get("upcoming_pipeline")),
                "estimated_opportunity_value": text(row.get("estimated_opportunity_value")),
                "catalogue_fit_status": text(row.get("catalogue_fit_status")),
                "catalogue_matched_events": text(row.get("catalogue_matched_events")),
                "catalogue_matched_products": text(row.get("catalogue_matched_products")),
                "procurement_event_ids": "; ".join(event_ids),
                "familiarity_evidence_ids": text(row.get("familiarity_evidence_ids")),
                "priority_reason": text(row.get("priority_reason")),
            }
        )

    return sorted(
        output,
        key=lambda row: (
            -number(row["commercial_account_priority_score"]),
            parse_date(row["action_due_date"]) or date.max,
            text(row["account_name"]).lower(),
        ),
    )


def write_action_queue(output_path: Path, priority_path: Path, today: date | None = None) -> int:
    rows = build_action_queue(load_csv(priority_path), today=today)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--priority", default="data/commercial_account_priority.csv")
    parser.add_argument("--output", default="data/commercial_action_queue.csv")
    args = parser.parse_args()
    count = write_action_queue(Path(args.output), Path(args.priority))
    print(f"Commercial action queue completed: {count} actions")


if __name__ == "__main__":
    main()
