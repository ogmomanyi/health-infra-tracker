"""Account-level operational views over persistent commercial CRM state."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from procurement_intelligence import commercial_crm, commercial_work


def list_accounts(db_path: Path | str = commercial_crm.DB_DEFAULT, today: str | None = None) -> list[dict[str, object]]:
    """Aggregate active CRM opportunities by canonical target account."""
    work = commercial_work.list_work(db_path=db_path, today=today)["items"]
    accounts: dict[str, dict[str, object]] = {}
    for row in work:
        account_id = str(row.get("target_account_id") or row.get("account_name") or row["opportunity_id"])
        account = accounts.setdefault(account_id, {
            "target_account_id": account_id,
            "account_name": row.get("account_name") or "Unknown account",
            "country": row.get("country") or "",
            "account_type": row.get("account_type") or "",
            "opportunities": [],
            "active_opportunities": 0,
            "outstanding_actions": 0,
            "overdue_actions": 0,
            "highest_priority_score": None,
            "highest_priority_tier": "",
        })
        score = row.get("commercial_account_priority_score")
        if score is not None and (account["highest_priority_score"] is None or float(score) > float(account["highest_priority_score"])):
            account["highest_priority_score"] = score
            account["highest_priority_tier"] = row.get("commercial_account_priority_tier") or ""
        account["active_opportunities"] += 1
        if row.get("due_date"):
            account["outstanding_actions"] += 1
        if row.get("work_bucket") == "overdue":
            account["overdue_actions"] += 1
        account["opportunities"].append({
            "opportunity_id": row["opportunity_id"],
            "title": row.get("title"),
            "buyer": row.get("buyer"),
            "status": row.get("status"),
            "commercial_account_priority_score": score,
            "commercial_account_priority_tier": row.get("commercial_account_priority_tier"),
            "effective_next_activity": row.get("effective_next_activity"),
            "due_date": row.get("due_date"),
            "work_bucket": row.get("work_bucket"),
            "overdue": row.get("work_bucket") == "overdue",
        })
    result = list(accounts.values())
    for account in result:
        account["opportunities"].sort(key=lambda x: (not x["overdue"], -(float(x["commercial_account_priority_score"]) if x["commercial_account_priority_score"] is not None else 0)))
    result.sort(key=lambda x: (x["overdue_actions"] == 0, -(float(x["highest_priority_score"]) if x["highest_priority_score"] is not None else 0), str(x["account_name"])))
    return result
