from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from procurement_intelligence import commercial_crm, execution_completeness


def _seed(db_path: Path) -> str:
    opportunity_id = "OPP-APPROVAL-1"
    commercial_crm.sync_opportunities(
        [{
            "opportunity_id": opportunity_id,
            "target_account_id": "ACCT-1",
            "account_name": "Approval Test Hospital",
            "commercial_account_priority_score": "91.0",
            "commercial_account_priority_tier": "ACT_NOW",
        }],
        db_path,
    )
    return opportunity_id


def _case(**overrides):
    data = {
        "case_name": "Base case",
        "supplier_reference": "SUP-Q-001",
        "supplier_currency": "USD",
        "supplier_cost": 500,
        "pricing_currency": "USD",
        "freight_cost": 50,
        "clearing_and_tax_cost": 25,
        "financing_cost": 10,
        "other_costs": 15,
        "selling_price": 750,
        "cost_basis_complete": True,
        "created_by": "Edward",
    }
    data.update(overrides)
    return data


def test_pricing_approval_is_bound_to_an_immutable_revision():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "crm.db"
        opportunity_id = _seed(db_path)

        case_id = execution_completeness.upsert_pricing_case(
            opportunity_id, _case(), db_path
        )
        revision_one = execution_completeness.get_pricing_revision(
            opportunity_id, case_id, db_path=db_path
        )
        assert revision_one is not None
        assert revision_one["revision_number"] == 1
        assert revision_one["selling_price"] == 750
        assert revision_one["approval_status"] == "PENDING"

        approval = execution_completeness.record_pricing_approval(
            opportunity_id,
            case_id,
            1,
            "APPROVED",
            decided_by="Finance Director",
            rationale="Margin and payment terms accepted.",
            db_path=db_path,
        )
        assert approval["decision"] == "APPROVED"
        assert approval["revision_number"] == 1

        execution_completeness.upsert_pricing_case(
            opportunity_id,
            _case(pricing_case_id=case_id, selling_price=725),
            db_path,
        )
        current = execution_completeness.get_pricing_revision(
            opportunity_id, case_id, db_path=db_path
        )
        assert current is not None
        assert current["revision_number"] == 2
        assert current["selling_price"] == 725
        assert current["approval_status"] == "PENDING"

        preserved = execution_completeness.get_pricing_revision(
            opportunity_id, case_id, 1, db_path
        )
        assert preserved is not None
        assert preserved["selling_price"] == 750
        assert preserved["approval_status"] == "APPROVED"

        history = execution_completeness.list_pricing_approvals(
            opportunity_id, case_id, db_path
        )
        assert [(row["revision_number"], row["decision"]) for row in history] == [
            (1, "APPROVED")
        ]


def test_stale_revision_cannot_receive_a_new_approval_decision():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "crm.db"
        opportunity_id = _seed(db_path)
        case_id = execution_completeness.upsert_pricing_case(
            opportunity_id, _case(), db_path
        )
        execution_completeness.upsert_pricing_case(
            opportunity_id,
            _case(pricing_case_id=case_id, selling_price=725),
            db_path,
        )

        with pytest.raises(ValueError, match="current pricing case revision"):
            execution_completeness.record_pricing_approval(
                opportunity_id,
                case_id,
                1,
                "APPROVED",
                decided_by="Finance Director",
                db_path=db_path,
            )


def test_existing_pricing_case_is_backfilled_as_revision_one():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "crm.db"
        opportunity_id = _seed(db_path)
        with commercial_crm.connect(db_path) as conn:
            conn.executescript(
                """
                DROP TABLE IF EXISTS commercial_pricing_approvals;
                DROP TABLE IF EXISTS commercial_pricing_case_revisions;
                DROP TABLE IF EXISTS commercial_pricing_cases;
                CREATE TABLE commercial_pricing_cases (
                    pricing_case_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    opportunity_id TEXT NOT NULL REFERENCES opportunity_context(opportunity_id) ON DELETE CASCADE,
                    case_name TEXT NOT NULL,
                    supplier_reference TEXT, supplier_currency TEXT, supplier_cost REAL,
                    pricing_currency TEXT, fx_rate_to_pricing_currency REAL,
                    freight_cost REAL, clearing_and_tax_cost REAL, financing_cost REAL,
                    other_costs REAL, selling_price REAL,
                    cost_basis_complete INTEGER NOT NULL DEFAULT 0,
                    payment_terms TEXT, quote_valid_until TEXT, notes TEXT, created_by TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                INSERT INTO commercial_pricing_cases (
                    opportunity_id, case_name, supplier_currency, supplier_cost,
                    pricing_currency, selling_price, cost_basis_complete,
                    created_by, created_at, updated_at
                ) VALUES (?, 'Legacy case', 'USD', 500, 'USD', 750, 1,
                          'Edward', '2026-09-11T10:00:00+00:00', '2026-09-11T10:00:00+00:00')
                """,
                (opportunity_id,),
            )

        execution_completeness.initialize(db_path)
        cases = execution_completeness.list_pricing_cases(opportunity_id, db_path)
        assert cases[0]["current_revision_number"] == 1
        revision = execution_completeness.get_pricing_revision(
            opportunity_id, cases[0]["pricing_case_id"], db_path=db_path
        )
        assert revision is not None
        assert revision["case_name"] == "Legacy case"
        assert revision["created_at"] == "2026-09-11T10:00:00+00:00"
