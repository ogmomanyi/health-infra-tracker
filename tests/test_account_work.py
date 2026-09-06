from pathlib import Path
from tempfile import TemporaryDirectory
from procurement_intelligence import account_work, commercial_crm


def _seed(db_path: Path) -> None:
    commercial_crm.sync_opportunities([
        {"opportunity_id":"OPP-1","target_account_id":"A1","account_name":"Alpha Hospital","country":"KE","account_type":"Hospital","commercial_account_priority_score":"82","commercial_account_priority_tier":"ACT_NOW","action_category":"QUALIFY_AND_BID","next_activity":"Call buyer","next_activity_due_date":"2026-09-01"},
        {"opportunity_id":"OPP-2","target_account_id":"A1","account_name":"Alpha Hospital","country":"KE","account_type":"Hospital","commercial_account_priority_score":"61","commercial_account_priority_tier":"PRIORITISE","action_category":"BID_PREPARATION","next_activity":"Prepare quote","next_activity_due_date":"2026-09-10"},
        {"opportunity_id":"OPP-3","target_account_id":"B2","account_name":"Beta Clinic","country":"UG","account_type":"Clinic","commercial_account_priority_score":"45","commercial_account_priority_tier":"DEVELOP","action_category":"PIPELINE_DEVELOPMENT","next_activity":"Research account"},
    ], db_path)


def test_accounts_aggregate_active_work_and_preserve_priority():
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "crm.db"
        _seed(db)
        accounts = account_work.list_accounts(db, today="2026-09-06")
        assert accounts[0]["account_name"] == "Alpha Hospital"
        assert accounts[0]["active_opportunities"] == 2
        assert accounts[0]["outstanding_actions"] == 2
        assert accounts[0]["overdue_actions"] == 1
        assert accounts[0]["highest_priority_score"] == 82.0
        assert accounts[0]["highest_priority_tier"] == "ACT_NOW"
        assert accounts[0]["opportunities"][0]["commercial_account_priority_score"] == 82.0
        assert len(accounts) == 2


def test_completed_opportunity_is_not_in_account_work():
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "crm.db"
        _seed(db)
        commercial_crm.update_state("OPP-1", db_path=db, status="WON")
        accounts = account_work.list_accounts(db, today="2026-09-06")
        alpha = next(a for a in accounts if a["account_name"] == "Alpha Hospital")
        assert alpha["active_opportunities"] == 1
        assert all(o["opportunity_id"] != "OPP-1" for o in alpha["opportunities"])
