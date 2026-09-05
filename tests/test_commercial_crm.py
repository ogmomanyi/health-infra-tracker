from pathlib import Path

from procurement_intelligence.commercial_crm import (
    add_activity,
    get_opportunity,
    initialize,
    list_activities,
    list_audit_log,
    list_opportunities,
    sync_opportunities,
    update_state,
)


def workspace_rows():
    return [
        {
            "opportunity_id": "OPP-E1",
            "action_id": "ACTION-E1",
            "target_account_id": "ACC-1",
            "account_name": "Buyer One",
            "country": "Kenya",
            "account_type": "Government",
            "crm_stage": "Target",
            "commercial_account_priority_score": "82",
            "commercial_account_priority_tier": "ACT_NOW",
            "action_category": "QUALIFY_AND_BID",
            "action_status": "OPEN",
            "next_activity": "Qualify tender",
            "next_activity_due_date": "2026-09-10",
            "procurement_event_id": "E1",
            "tender_reference": "T-1",
            "title": "Lab equipment",
            "buyer": "Buyer One",
            "procurement_stage": "OPEN",
            "publication_date": "2026-09-01",
            "closing_date": "2026-09-20",
            "days_to_closing": "15",
            "estimated_value": "100000",
            "currency": "KES",
            "equipment_category": "Analyzer",
            "product_family": "Chemistry Analyzer",
            "catalogue_fit_status": "FARAM_MATCH",
            "catalogue_matched_products": "Product A",
            "source": "UNGM",
            "source_url": "https://example.test/tender",
            "priority_reason": "High demand and verified fit",
            "recommended_action": "Qualify tender",
            "familiarity_evidence_ids": "HQE-001",
        }
    ]


def test_sync_creates_context_and_default_state(tmp_path: Path):
    db = tmp_path / "crm.db"
    assert sync_opportunities(workspace_rows(), db) == 1
    row = get_opportunity("OPP-E1", db)
    assert row["commercial_account_priority_score"] == 82.0
    assert row["status"] == "OPEN"
    assert row["assigned_owner"] is None


def test_sync_preserves_mutable_state(tmp_path: Path):
    db = tmp_path / "crm.db"
    sync_opportunities(workspace_rows(), db)
    update_state("OPP-E1", db_path=db, actor="edward", status="QUALIFIED", assigned_owner="Edward")
    rows = workspace_rows()
    rows[0]["commercial_account_priority_score"] = "91"
    rows[0]["recommended_action"] = "Prepare bid"
    sync_opportunities(rows, db)
    row = get_opportunity("OPP-E1", db)
    assert row["commercial_account_priority_score"] == 91.0
    assert row["recommended_action"] == "Prepare bid"
    assert row["status"] == "QUALIFIED"
    assert row["assigned_owner"] == "Edward"


def test_state_updates_and_audit(tmp_path: Path):
    db = tmp_path / "crm.db"
    sync_opportunities(workspace_rows(), db)
    update_state(
        "OPP-E1",
        db_path=db,
        actor="edward",
        status="BID_NO_BID",
        next_activity="Confirm bid decision",
        next_activity_due_date="2026-09-08",
        notes="Awaiting principal confirmation",
    )
    row = get_opportunity("OPP-E1", db)
    assert row["status"] == "BID_NO_BID"
    assert row["next_activity_override"] == "Confirm bid decision"
    assert len(list_audit_log("OPP-E1", db)) >= 4


def test_activity_is_persistent_and_audited(tmp_path: Path):
    db = tmp_path / "crm.db"
    sync_opportunities(workspace_rows(), db)
    activity_id = add_activity(
        "OPP-E1",
        "CALL",
        "Spoke with procurement contact",
        db_path=db,
        notes="Confirmed tender timetable",
        owner="Edward",
        actor="edward",
    )
    activities = list_activities("OPP-E1", db)
    assert activities[0]["activity_id"] == activity_id
    assert activities[0]["subject"] == "Spoke with procurement contact"
    assert any(row["change_type"] == "ACTIVITY_ADDED" for row in list_audit_log("OPP-E1", db))


def test_list_filters(tmp_path: Path):
    db = tmp_path / "crm.db"
    sync_opportunities(workspace_rows(), db)
    update_state("OPP-E1", db_path=db, status="QUALIFIED", assigned_owner="Edward")
    assert len(list_opportunities(db, status="QUALIFIED")) == 1
    assert len(list_opportunities(db, owner="Edward")) == 1
    assert len(list_opportunities(db, status="LOST")) == 0


def test_unknown_opportunity_rejected(tmp_path: Path):
    db = tmp_path / "crm.db"
    initialize(db)
    try:
        update_state("OPP-MISSING", db_path=db, status="LOST")
    except KeyError as exc:
        assert "OPP-MISSING" in str(exc)
    else:
        raise AssertionError("Expected KeyError")
