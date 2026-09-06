"""Operational work-queue views over persistent commercial CRM state.

This layer deliberately does not calculate commercial priority. It inherits the
canonical priority score/tier from commercial_crm opportunity context.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from procurement_intelligence import commercial_crm


def list_work(
    db_path: Path | str = commercial_crm.DB_DEFAULT,
    owner: str | None = None,
    today: str | None = None,
) -> dict[str, object]:
    """Return active opportunities grouped by next-activity due date."""
    today_date = (
        datetime.fromisoformat(today).date()
        if today
        else datetime.now(timezone.utc).date()
    )
    week_end = today_date + timedelta(days=6)
    completed = {"WON", "LOST"}
    items: list[dict[str, object]] = []

    for row in commercial_crm.list_opportunities(db_path=db_path, owner=owner):
        if row["status"] in completed:
            continue

        due = row["next_activity_due_date_override"] or row["next_activity_due_date"]
        due_date = None
        if due:
            try:
                due_date = datetime.fromisoformat(str(due)).date()
            except ValueError:
                pass

        if due_date and due_date < today_date:
            bucket = "overdue"
        elif due_date == today_date:
            bucket = "today"
        elif due_date and today_date < due_date <= week_end:
            bucket = "week"
        else:
            bucket = "later"

        item = dict(row)
        item["effective_next_activity"] = (
            row["next_activity_override"] or row["next_activity"] or "Review account action"
        )
        item["due_date"] = due
        item["work_bucket"] = bucket
        items.append(item)

    bucket_order = {"overdue": 0, "today": 1, "week": 2, "later": 3}
    items.sort(
        key=lambda item: (
            bucket_order[item["work_bucket"]],
            item["due_date"] or "9999-12-31",
            -(float(item["commercial_account_priority_score"])
              if item["commercial_account_priority_score"] is not None else 0),
        )
    )
    summary = {
        "active": len(items),
        "overdue": sum(item["work_bucket"] == "overdue" for item in items),
        "today": sum(item["work_bucket"] == "today" for item in items),
        "week": sum(item["work_bucket"] == "week" for item in items),
        "unassigned": sum(not item["assigned_owner"] for item in items),
    }
    return {"as_of": today_date.isoformat(), "summary": summary, "items": items}
