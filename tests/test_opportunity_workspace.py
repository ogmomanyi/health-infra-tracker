from pathlib import Path
from tempfile import TemporaryDirectory

from procurement_intelligence import commercial_crm


def test_opportunity_detail_preserves_canonical_context_after_state_changes():
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "crm.db"
        commercial_crm.sync_opportunities([{
            "opportunity_id": "OPP-1",
            "target_account_id": "A1",
            "account_name": "Alpha Hospital",
            "country": "KE",
            "title": "Lab equipment tender",
            "buyer": "Alpha Hospital",
            "commercial_account_priority_score": "88.5",
            "commercial_account_priority_tier": "ACT_NOW",
            "closing_date": "2026-09-10",
            "catalogue_fit_status": "FARAM_MATCH",
            "catalogue_matched_products": "Analyzer X",
            "recommended_action": "Contact buyer",
        }], db)
        commercial_crm.update_state("OPP-1", db_path=db, status="QUALIFIED", assigned_owner="Edward", notes="Buyer contacted")
        commercial_crm.add_activity("OPP-1", "CALL", "Buyer call", db_path=db, owner="Edward")

        item = commercial_crm.get_opportunity("OPP-1", db)
        assert item["status"] == "QUALIFIED"
        assert item["assigned_owner"] == "Edward"
        assert item["commercial_account_priority_score"] == 88.5
        assert item["commercial_account_priority_tier"] == "ACT_NOW"
        assert item["catalogue_fit_status"] == "FARAM_MATCH"
        assert item["closing_date"] == "2026-09-10"
        assert commercial_crm.list_activities("OPP-1", db)[0]["subject"] == "Buyer call"
        assert any(row["field_name"] == "status" for row in commercial_crm.list_audit_log("OPP-1", db))
