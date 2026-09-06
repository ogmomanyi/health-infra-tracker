from pathlib import Path
from tempfile import TemporaryDirectory
from procurement_intelligence import commercial_crm, management_work


def _seed(db_path: Path) -> None:
    commercial_crm.sync_opportunities([
        {"opportunity_id":"OPP-1","target_account_id":"A1","account_name":"Alpha","status":"OPEN","commercial_account_priority_score":"90","commercial_account_priority_tier":"ACT_NOW","next_activity":"Call","next_activity_due_date":"2026-09-01","closing_date":"2026-09-08","estimated_value":"1000","currency":"USD"},
        {"opportunity_id":"OPP-2","target_account_id":"A2","account_name":"Beta","commercial_account_priority_score":"80","commercial_account_priority_tier":"ACT_NOW","next_activity":"Quote","next_activity_due_date":"2026-09-07","closing_date":"2026-09-20","estimated_value":"2000","currency":"USD"},
        {"opportunity_id":"OPP-3","target_account_id":"A3","account_name":"Gamma","commercial_account_priority_score":"40","commercial_account_priority_tier":"DEVELOP","next_activity":"Research","next_activity_due_date":"2026-09-10","closing_date":"2026-09-30"},
        {"opportunity_id":"OPP-4","target_account_id":"A4","account_name":"Delta","commercial_account_priority_score":"70","commercial_account_priority_tier":"PRIORITISE","closing_date":"2026-09-06"},
    ], db_path)
    commercial_crm.update_state("OPP-2", db_path=db_path, assigned_owner="Alice")
    commercial_crm.update_state("OPP-3", db_path=db_path, assigned_owner="Bob")
    commercial_crm.update_state("OPP-4", db_path=db_path, status="WON")


def test_management_summary_groups_pipeline_and_workload():
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "crm.db"
        _seed(db)
        result = management_work.management_summary(db, today="2026-09-06")
        assert result["summary"] == {
            "active_opportunities": 3,
            "accounts": 3,
            "overdue_actions": 1,
            "closing_soon": 1,
            "won": 1,
            "lost": 0,
            "high_priority_unassigned": 1,
        }
        assert {item["owner"]: item["count"] for item in result["work_by_owner"]} == {"Unassigned": 1, "Alice": 1, "Bob": 1}
        assert result["pipeline_by_stage"] == [{"stage": "OPEN", "count": 3}]
        assert result["closing_soon"][0]["opportunity_id"] == "OPP-1"
        assert result["high_priority_unassigned"][0]["opportunity_id"] == "OPP-1"
        assert result["high_priority_unassigned"][0]["commercial_account_priority_score"] == 90.0


def test_management_does_not_recalculate_priority():
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "crm.db"
        _seed(db)
        before = commercial_crm.get_opportunity("OPP-1", db)["commercial_account_priority_score"]
        management_work.management_summary(db, today="2026-09-06")
        after = commercial_crm.get_opportunity("OPP-1", db)["commercial_account_priority_score"]
        assert before == after == 90.0
