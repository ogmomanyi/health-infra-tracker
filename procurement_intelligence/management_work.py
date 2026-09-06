"""Management-level summaries over persistent commercial CRM state.

This layer reports operational workload and pipeline. It never recalculates
commercial priority; score and tier are inherited from canonical opportunity context.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from procurement_intelligence import commercial_crm, commercial_work


def _date(value: object) -> datetime.date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def management_summary(
    db_path: Path | str = commercial_crm.DB_DEFAULT,
    today: str | None = None,
    closing_window_days: int = 7,
) -> dict[str, object]:
    """Return management KPIs, pipeline, workload and closing-soon views."""
    today_date = (
        datetime.fromisoformat(today).date() if today else datetime.now(timezone.utc).date()
    )
    closing_end = today_date + timedelta(days=closing_window_days)
    rows = commercial_crm.list_opportunities(db_path=db_path)
    active_statuses = set(commercial_crm.OPPORTUNITY_STATUSES) - {"WON", "LOST"}
    active = [row for row in rows if row["status"] in active_statuses]
    work = commercial_work.list_work(db_path=db_path, today=today_date.isoformat())["items"]

    by_stage: dict[str, int] = {}
    by_owner: dict[str, int] = {}
    value_by_currency: dict[str, float] = {}
    for row in active:
        stage = str(row.get("status") or "UNKNOWN")
        by_stage[stage] = by_stage.get(stage, 0) + 1
        owner = str(row.get("assigned_owner") or "Unassigned")
        by_owner[owner] = by_owner.get(owner, 0) + 1
        if row.get("estimated_value") is not None:
            currency = str(row.get("currency") or "UNSPECIFIED")
            value_by_currency[currency] = value_by_currency.get(currency, 0.0) + float(row["estimated_value"])

    closing_soon = []
    for row in active:
        closing = _date(row.get("closing_date"))
        if closing is not None and today_date <= closing <= closing_end:
            item = dict(row)
            item["closing_date"] = closing.isoformat()
            item["days_to_closing"] = (closing - today_date).days
            closing_soon.append(item)
    closing_soon.sort(key=lambda row: (row["days_to_closing"], -(float(row["commercial_account_priority_score"]) if row["commercial_account_priority_score"] is not None else 0)))

    overdue = [row for row in work if row["work_bucket"] == "overdue"]
    high_priority_unassigned = [
        row for row in active
        if not row.get("assigned_owner") and row.get("commercial_account_priority_tier") == "ACT_NOW"
    ]
    high_priority_unassigned.sort(key=lambda row: -(float(row["commercial_account_priority_score"]) if row["commercial_account_priority_score"] is not None else 0))

    return {
        "as_of": today_date.isoformat(),
        "closing_window_days": closing_window_days,
        "summary": {
            "active_opportunities": len(active),
            "accounts": len({row.get("target_account_id") or row.get("account_name") for row in active}),
            "overdue_actions": len(overdue),
            "closing_soon": len(closing_soon),
            "won": sum(row["status"] == "WON" for row in rows),
            "lost": sum(row["status"] == "LOST" for row in rows),
            "high_priority_unassigned": len(high_priority_unassigned),
        },
        "pipeline_by_stage": [{"stage": key, "count": value} for key, value in sorted(by_stage.items())],
        "work_by_owner": [{"owner": key, "count": value} for key, value in sorted(by_owner.items(), key=lambda item: (-item[1], item[0]))],
        "estimated_value_by_currency": [{"currency": key, "value": value} for key, value in sorted(value_by_currency.items())],
        "overdue": overdue,
        "closing_soon": closing_soon,
        "high_priority_unassigned": high_priority_unassigned,
    }
