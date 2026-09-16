from pathlib import Path

from procurement_intelligence import commercial_crm, project_follow_up


def _write_projects(path: Path):
    path.write_text(
        "iati_identifier,project_title,reporting_org_name,funding_agencies,implementing_partners,country_codes,country_names,activity_status_label,last_updated,budget_usd,future_disbursement_usd,next_disbursement_date,equipment_target_summary,direct_equipment_categories,opportunity_score,priority_band,signal_summary,tender_stage,recommended_action\n"
        'IATI/KE/001,"County laboratory upgrade",Reporter,Donor,"County Health Department",KE,Kenya,Active,2026-09-01,100000,75000,2026-12-31,"Laboratory Equipment","Hematology Analyzer",91,Strategic Priority,"equipment demand; funding window",Likely procurement,"Confirm buyer and specifications."\n',
        encoding="utf-8",
    )


def test_project_selection_creates_durable_workflow(tmp_path):
    projects = tmp_path / "opportunities.csv"
    db = tmp_path / "crm.db"
    _write_projects(projects)

    result = project_follow_up.track_project(
        "IATI/KE/001", projects_path=projects, db_path=db, owner="Edward",
        next_activity="Call the county laboratory lead", due_date="2026-09-23",
        selection_reason="Strong funded equipment signal", selected_by="test-user",
    )

    opportunity = result["opportunity"]
    assert opportunity["assigned_owner"] == "Edward"
    assert opportunity["next_activity_override"] == "Call the county laboratory lead"
    assert opportunity["next_activity_due_date_override"] == "2026-09-23"
    assert opportunity["commercial_account_priority_score"] == 91
    assert opportunity["commercial_account_priority_tier"] == "ACT_NOW"
    assert commercial_crm.list_activities(opportunity["opportunity_id"], db)[0]["activity_type"] == "PROJECT_SELECTED"

    listed = project_follow_up.list_projects(projects_path=projects, db_path=db)
    assert listed["summary"]["tracked"] == 1
    assert listed["projects"][0]["tracked"] is True
    assert listed["projects"][0]["workflow_next_activity"] == "Call the county laboratory lead"


def test_reselecting_project_is_idempotent(tmp_path):
    projects = tmp_path / "opportunities.csv"
    db = tmp_path / "crm.db"
    _write_projects(projects)
    first = project_follow_up.track_project("IATI/KE/001", projects_path=projects, db_path=db)
    second = project_follow_up.track_project("IATI/KE/001", projects_path=projects, db_path=db)

    assert first["opportunity"]["opportunity_id"] == second["opportunity"]["opportunity_id"]
    assert len(commercial_crm.list_tracked_projects(db)) == 1
    assert len(commercial_crm.list_activities(first["opportunity"]["opportunity_id"], db)) == 1
