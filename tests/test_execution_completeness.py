from pathlib import Path
from tempfile import TemporaryDirectory

from procurement_intelligence import commercial_crm, execution_completeness


def test_execution_completeness_persists_without_changing_canonical_priority():
    with TemporaryDirectory() as tmp:
        db = Path(tmp) / "crm.db"
        commercial_crm.sync_opportunities([{
            "opportunity_id": "OPP-1",
            "target_account_id": "A1",
            "account_name": "Alpha Hospital",
            "commercial_account_priority_score": "91.5",
            "commercial_account_priority_tier": "ACT_NOW",
            "title": "Analyzer tender",
        }], db)
        execution_completeness.upsert_contact("OPP-1", {"contact_type": "PROCUREMENT", "name": "Jane Buyer", "email": "jane@example.org"}, db)
        execution_completeness.set_bid_decision("OPP-1", "BID", decided_by="Edward", rationale="Strong fit")
        execution_completeness.add_response("OPP-1", {"response_type": "QUOTE", "reference": "Q-001", "value": 125000, "currency": "USD"}, db)
        execution_completeness.add_evidence("OPP-1", {"evidence_type": "TENDER", "title": "Tender notice", "location": "https://example.org/tender"}, db)
        execution_completeness.record_outcome("OPP-1", {"outcome": "WON", "reason": "Best technical fit", "recorded_by": "Edward"}, db)

        snapshot = execution_completeness.snapshot("OPP-1", db)
        context = commercial_crm.get_opportunity("OPP-1", db)
        assert context["commercial_account_priority_score"] == 91.5
        assert context["commercial_account_priority_tier"] == "ACT_NOW"
        assert snapshot["contacts"][0]["name"] == "Jane Buyer"
        assert snapshot["bid_decision"]["decision"] == "BID"
        assert snapshot["responses"][0]["reference"] == "Q-001"
        assert snapshot["evidence"][0]["title"] == "Tender notice"
        assert snapshot["outcome"]["outcome"] == "WON"
