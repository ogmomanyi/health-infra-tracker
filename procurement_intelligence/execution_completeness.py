"""Persistent commercial execution completeness state.

This layer stores execution facts that are neither generated intelligence nor the
canonical commercial priority score: buyer contacts, bid/no-bid decisions,
commercial responses, evidence records, and opportunity outcomes.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from procurement_intelligence import commercial_crm

CONTACT_TYPES = ("PRIMARY_BUYER", "TECHNICAL", "PROCUREMENT", "FINANCE", "OTHER")
DECISIONS = ("PENDING", "BID", "NO_BID")
EVIDENCE_TYPES = ("TENDER", "SPECIFICATION", "QUOTE", "EMAIL", "MEETING", "OTHER")
OUTCOME_TYPES = ("WON", "LOST", "CANCELLED", "NO_DECISION")
PRICING_APPROVAL_DECISIONS = ("APPROVED", "REJECTED", "CHANGES_REQUESTED")

PRICING_FIELDS = (
    "case_name",
    "supplier_reference",
    "supplier_currency",
    "supplier_cost",
    "pricing_currency",
    "fx_rate_to_pricing_currency",
    "freight_cost",
    "clearing_and_tax_cost",
    "financing_cost",
    "other_costs",
    "selling_price",
    "cost_basis_complete",
    "payment_terms",
    "quote_valid_until",
    "notes",
    "created_by",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def initialize(db_path: Path | str = commercial_crm.DB_DEFAULT) -> None:
    """Create completeness tables in the existing CRM database."""
    commercial_crm.initialize(db_path)
    with commercial_crm.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS opportunity_contacts (
                contact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                opportunity_id TEXT NOT NULL REFERENCES opportunity_context(opportunity_id) ON DELETE CASCADE,
                contact_type TEXT NOT NULL,
                name TEXT NOT NULL,
                organisation TEXT,
                email TEXT,
                phone TEXT,
                role TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_contacts_opportunity ON opportunity_contacts(opportunity_id, updated_at DESC);

            CREATE TABLE IF NOT EXISTS bid_decisions (
                opportunity_id TEXT PRIMARY KEY REFERENCES opportunity_context(opportunity_id) ON DELETE CASCADE,
                decision TEXT NOT NULL CHECK(decision IN ('PENDING','BID','NO_BID')) DEFAULT 'PENDING',
                decided_by TEXT,
                decided_at TEXT,
                rationale TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS commercial_responses (
                response_id INTEGER PRIMARY KEY AUTOINCREMENT,
                opportunity_id TEXT NOT NULL REFERENCES opportunity_context(opportunity_id) ON DELETE CASCADE,
                response_type TEXT NOT NULL,
                reference TEXT,
                value REAL,
                currency TEXT,
                submitted_date TEXT,
                valid_until TEXT,
                status TEXT NOT NULL DEFAULT 'DRAFT',
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_responses_opportunity ON commercial_responses(opportunity_id, updated_at DESC);

            CREATE TABLE IF NOT EXISTS execution_evidence (
                evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                opportunity_id TEXT NOT NULL REFERENCES opportunity_context(opportunity_id) ON DELETE CASCADE,
                evidence_type TEXT NOT NULL,
                title TEXT NOT NULL,
                location TEXT,
                recorded_date TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_evidence_opportunity ON execution_evidence(opportunity_id, recorded_date DESC, evidence_id DESC);

            CREATE TABLE IF NOT EXISTS commercial_pricing_cases (
                pricing_case_id INTEGER PRIMARY KEY AUTOINCREMENT,
                opportunity_id TEXT NOT NULL REFERENCES opportunity_context(opportunity_id) ON DELETE CASCADE,
                case_name TEXT NOT NULL,
                supplier_reference TEXT,
                supplier_currency TEXT,
                supplier_cost REAL,
                pricing_currency TEXT,
                fx_rate_to_pricing_currency REAL,
                freight_cost REAL,
                clearing_and_tax_cost REAL,
                financing_cost REAL,
                other_costs REAL,
                selling_price REAL,
                cost_basis_complete INTEGER NOT NULL DEFAULT 0,
                payment_terms TEXT,
                quote_valid_until TEXT,
                notes TEXT,
                created_by TEXT,
                current_revision_number INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_pricing_cases_opportunity ON commercial_pricing_cases(opportunity_id, updated_at DESC, pricing_case_id DESC);

            CREATE TABLE IF NOT EXISTS commercial_pricing_case_revisions (
                revision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                pricing_case_id INTEGER NOT NULL REFERENCES commercial_pricing_cases(pricing_case_id) ON DELETE CASCADE,
                opportunity_id TEXT NOT NULL REFERENCES opportunity_context(opportunity_id) ON DELETE CASCADE,
                revision_number INTEGER NOT NULL,
                case_name TEXT NOT NULL,
                supplier_reference TEXT,
                supplier_currency TEXT,
                supplier_cost REAL,
                pricing_currency TEXT,
                fx_rate_to_pricing_currency REAL,
                freight_cost REAL,
                clearing_and_tax_cost REAL,
                financing_cost REAL,
                other_costs REAL,
                selling_price REAL,
                cost_basis_complete INTEGER NOT NULL DEFAULT 0,
                payment_terms TEXT,
                quote_valid_until TEXT,
                notes TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(pricing_case_id, revision_number)
            );
            CREATE INDEX IF NOT EXISTS idx_pricing_revisions_case
                ON commercial_pricing_case_revisions(pricing_case_id, revision_number DESC);

            CREATE TABLE IF NOT EXISTS commercial_pricing_approvals (
                approval_id INTEGER PRIMARY KEY AUTOINCREMENT,
                opportunity_id TEXT NOT NULL REFERENCES opportunity_context(opportunity_id) ON DELETE CASCADE,
                pricing_case_id INTEGER NOT NULL REFERENCES commercial_pricing_cases(pricing_case_id) ON DELETE CASCADE,
                revision_id INTEGER NOT NULL REFERENCES commercial_pricing_case_revisions(revision_id) ON DELETE RESTRICT,
                revision_number INTEGER NOT NULL,
                decision TEXT NOT NULL CHECK(decision IN ('APPROVED','REJECTED','CHANGES_REQUESTED')),
                decided_by TEXT NOT NULL,
                rationale TEXT,
                decided_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_pricing_approvals_revision
                ON commercial_pricing_approvals(revision_id, approval_id DESC);
            CREATE INDEX IF NOT EXISTS idx_pricing_approvals_opportunity
                ON commercial_pricing_approvals(opportunity_id, decided_at DESC, approval_id DESC);

            CREATE TABLE IF NOT EXISTS opportunity_outcomes (
                opportunity_id TEXT PRIMARY KEY REFERENCES opportunity_context(opportunity_id) ON DELETE CASCADE,
                outcome TEXT NOT NULL CHECK(outcome IN ('WON','LOST','CANCELLED','NO_DECISION')),
                outcome_date TEXT,
                value REAL,
                currency TEXT,
                reason TEXT,
                competitor TEXT,
                lessons TEXT,
                recorded_by TEXT,
                recorded_at TEXT NOT NULL
            );
            """
        )
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(commercial_pricing_cases)").fetchall()
        }
        if "current_revision_number" not in columns:
            conn.execute(
                "ALTER TABLE commercial_pricing_cases "
                "ADD COLUMN current_revision_number INTEGER NOT NULL DEFAULT 0"
            )
        # Existing pricing cases predate revision tracking. Preserve their current
        # values as immutable revision 1 instead of silently discarding history.
        revision_fields = ", ".join(PRICING_FIELDS)
        conn.execute(
            f"""
            INSERT INTO commercial_pricing_case_revisions (
                pricing_case_id, opportunity_id, revision_number,
                {revision_fields}, created_at
            )
            SELECT pricing_case_id, opportunity_id, 1,
                   {revision_fields}, updated_at
            FROM commercial_pricing_cases AS cases
            WHERE NOT EXISTS (
                SELECT 1
                FROM commercial_pricing_case_revisions AS revisions
                WHERE revisions.pricing_case_id = cases.pricing_case_id
            )
            """
        )
        conn.execute(
            """
            UPDATE commercial_pricing_cases
            SET current_revision_number = COALESCE((
                SELECT MAX(revision_number)
                FROM commercial_pricing_case_revisions AS revisions
                WHERE revisions.pricing_case_id = commercial_pricing_cases.pricing_case_id
            ), 0)
            WHERE current_revision_number = 0
            """
        )


def _ensure_opportunity(opportunity_id: str, db_path: Path | str) -> None:
    if commercial_crm.get_opportunity(opportunity_id, db_path=db_path) is None:
        raise KeyError(f"Unknown opportunity: {opportunity_id}")


def list_contacts(opportunity_id: str, db_path: Path | str = commercial_crm.DB_DEFAULT) -> list[dict[str, object]]:
    initialize(db_path)
    with commercial_crm.connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM opportunity_contacts WHERE opportunity_id = ? ORDER BY updated_at DESC, contact_id DESC", (opportunity_id,)).fetchall()
    return [dict(r) for r in rows]


def upsert_contact(opportunity_id: str, data: Mapping[str, object], db_path: Path | str = commercial_crm.DB_DEFAULT) -> int:
    initialize(db_path); _ensure_opportunity(opportunity_id, db_path)
    contact_type = str(data.get("contact_type") or "OTHER")
    if contact_type not in CONTACT_TYPES: raise ValueError(f"Unsupported contact type: {contact_type}")
    name = str(data.get("name") or "").strip()
    if not name: raise ValueError("Contact name is required")
    now = utc_now(); cid = data.get("contact_id")
    with commercial_crm.connect(db_path) as conn:
        if cid:
            conn.execute("""UPDATE opportunity_contacts SET contact_type=?, name=?, organisation=?, email=?, phone=?, role=?, notes=?, updated_at=? WHERE contact_id=? AND opportunity_id=?""", (contact_type,name,data.get("organisation"),data.get("email"),data.get("phone"),data.get("role"),data.get("notes"),now,cid,opportunity_id))
            return int(cid)
        cur = conn.execute("""INSERT INTO opportunity_contacts(opportunity_id,contact_type,name,organisation,email,phone,role,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""", (opportunity_id,contact_type,name,data.get("organisation"),data.get("email"),data.get("phone"),data.get("role"),data.get("notes"),now,now))
        return int(cur.lastrowid)


def get_bid_decision(opportunity_id: str, db_path: Path | str = commercial_crm.DB_DEFAULT) -> dict[str, object]:
    initialize(db_path); _ensure_opportunity(opportunity_id, db_path)
    with commercial_crm.connect(db_path) as conn:
        row = conn.execute("SELECT * FROM bid_decisions WHERE opportunity_id = ?", (opportunity_id,)).fetchone()
        if row: return dict(row)
    return {"opportunity_id": opportunity_id, "decision": "PENDING", "decided_by": None, "decided_at": None, "rationale": None, "updated_at": None}


def set_bid_decision(opportunity_id: str, decision: str, *, decided_by: str | None = None, rationale: str | None = None, db_path: Path | str = commercial_crm.DB_DEFAULT) -> dict[str, object]:
    initialize(db_path); _ensure_opportunity(opportunity_id, db_path)
    if decision not in DECISIONS: raise ValueError(f"Unsupported bid decision: {decision}")
    now = utc_now(); decided_at = now if decision != "PENDING" else None
    with commercial_crm.connect(db_path) as conn:
        conn.execute("""INSERT INTO bid_decisions(opportunity_id,decision,decided_by,decided_at,rationale,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(opportunity_id) DO UPDATE SET decision=excluded.decision,decided_by=excluded.decided_by,decided_at=excluded.decided_at,rationale=excluded.rationale,updated_at=excluded.updated_at""", (opportunity_id,decision,decided_by,decided_at,rationale,now))
    return get_bid_decision(opportunity_id, db_path)


def list_responses(opportunity_id: str, db_path: Path | str = commercial_crm.DB_DEFAULT) -> list[dict[str, object]]:
    initialize(db_path)
    with commercial_crm.connect(db_path) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM commercial_responses WHERE opportunity_id = ? ORDER BY updated_at DESC, response_id DESC", (opportunity_id,)).fetchall()]


def add_response(opportunity_id: str, data: Mapping[str, object], db_path: Path | str = commercial_crm.DB_DEFAULT) -> int:
    initialize(db_path); _ensure_opportunity(opportunity_id, db_path)
    now = utc_now()
    with commercial_crm.connect(db_path) as conn:
        cur = conn.execute("""INSERT INTO commercial_responses(opportunity_id,response_type,reference,value,currency,submitted_date,valid_until,status,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (opportunity_id,str(data.get("response_type") or "QUOTE"),data.get("reference"),data.get("value"),data.get("currency"),data.get("submitted_date"),data.get("valid_until"),str(data.get("status") or "DRAFT"),data.get("notes"),now,now))
        return int(cur.lastrowid)


def list_evidence(opportunity_id: str, db_path: Path | str = commercial_crm.DB_DEFAULT) -> list[dict[str, object]]:
    initialize(db_path)
    with commercial_crm.connect(db_path) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM execution_evidence WHERE opportunity_id = ? ORDER BY recorded_date DESC, evidence_id DESC", (opportunity_id,)).fetchall()]


def add_evidence(opportunity_id: str, data: Mapping[str, object], db_path: Path | str = commercial_crm.DB_DEFAULT) -> int:
    initialize(db_path); _ensure_opportunity(opportunity_id, db_path)
    evidence_type = str(data.get("evidence_type") or "OTHER")
    if evidence_type not in EVIDENCE_TYPES: raise ValueError(f"Unsupported evidence type: {evidence_type}")
    title = str(data.get("title") or "").strip()
    if not title: raise ValueError("Evidence title is required")
    with commercial_crm.connect(db_path) as conn:
        cur = conn.execute("""INSERT INTO execution_evidence(opportunity_id,evidence_type,title,location,recorded_date,notes,created_at) VALUES(?,?,?,?,?,?,?)""", (opportunity_id,evidence_type,title,data.get("location"),data.get("recorded_date"),data.get("notes"),utc_now()))
        return int(cur.lastrowid)


def list_pricing_cases(opportunity_id: str, db_path: Path | str = commercial_crm.DB_DEFAULT) -> list[dict[str, object]]:
    initialize(db_path)
    with commercial_crm.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT cases.*, revisions.revision_id AS current_revision_id,
                   approvals.approval_id, approvals.decision AS approval_status,
                   approvals.decided_by AS approval_decided_by,
                   approvals.rationale AS approval_rationale,
                   approvals.decided_at AS approval_decided_at
            FROM commercial_pricing_cases AS cases
            LEFT JOIN commercial_pricing_case_revisions AS revisions
              ON revisions.pricing_case_id = cases.pricing_case_id
             AND revisions.revision_number = cases.current_revision_number
            LEFT JOIN commercial_pricing_approvals AS approvals
              ON approvals.approval_id = (
                  SELECT MAX(latest.approval_id)
                  FROM commercial_pricing_approvals AS latest
                  WHERE latest.revision_id = revisions.revision_id
              )
            WHERE cases.opportunity_id = ?
            ORDER BY cases.updated_at DESC, cases.pricing_case_id DESC
            """,
            (opportunity_id,),
        ).fetchall()
    result = [dict(row) for row in rows]
    for row in result:
        row["approval_status"] = row.get("approval_status") or "PENDING"
    return result


def get_pricing_revision(
    opportunity_id: str,
    pricing_case_id: int,
    revision_number: int | None = None,
    db_path: Path | str = commercial_crm.DB_DEFAULT,
) -> dict[str, object] | None:
    """Return an immutable pricing snapshot and its latest approval decision."""
    initialize(db_path)
    with commercial_crm.connect(db_path) as conn:
        if revision_number is None:
            current = conn.execute(
                """
                SELECT current_revision_number
                FROM commercial_pricing_cases
                WHERE opportunity_id = ? AND pricing_case_id = ?
                """,
                (opportunity_id, pricing_case_id),
            ).fetchone()
            if current is None:
                return None
            revision_number = int(current["current_revision_number"])
        row = conn.execute(
            """
            SELECT revisions.*, cases.current_revision_number,
                   current_revision.revision_id AS current_revision_id,
                   approvals.approval_id,
                   approvals.decision AS approval_status,
                   approvals.decided_by AS approval_decided_by,
                   approvals.rationale AS approval_rationale,
                   approvals.decided_at AS approval_decided_at
            FROM commercial_pricing_case_revisions AS revisions
            JOIN commercial_pricing_cases AS cases
              ON cases.pricing_case_id = revisions.pricing_case_id
             AND cases.opportunity_id = revisions.opportunity_id
            LEFT JOIN commercial_pricing_case_revisions AS current_revision
              ON current_revision.pricing_case_id = cases.pricing_case_id
             AND current_revision.revision_number = cases.current_revision_number
            LEFT JOIN commercial_pricing_approvals AS approvals
              ON approvals.approval_id = (
                  SELECT MAX(latest.approval_id)
                  FROM commercial_pricing_approvals AS latest
                  WHERE latest.revision_id = revisions.revision_id
              )
            WHERE revisions.opportunity_id = ?
              AND revisions.pricing_case_id = ?
              AND revisions.revision_number = ?
            """,
            (opportunity_id, pricing_case_id, revision_number),
        ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["is_current_revision"] = (
        int(result["revision_number"]) == int(result["current_revision_number"])
    )
    result["approval_status"] = result.get("approval_status") or "PENDING"
    return result


def list_pricing_approvals(
    opportunity_id: str,
    pricing_case_id: int,
    db_path: Path | str = commercial_crm.DB_DEFAULT,
) -> list[dict[str, object]]:
    initialize(db_path)
    with commercial_crm.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM commercial_pricing_approvals
            WHERE opportunity_id = ? AND pricing_case_id = ?
            ORDER BY approval_id DESC
            """,
            (opportunity_id, pricing_case_id),
        ).fetchall()
    return [dict(row) for row in rows]


def record_pricing_approval(
    opportunity_id: str,
    pricing_case_id: int,
    revision_number: int,
    decision: str,
    *,
    decided_by: str,
    rationale: str | None = None,
    db_path: Path | str = commercial_crm.DB_DEFAULT,
) -> dict[str, object]:
    """Append an approval decision for the current immutable pricing revision."""
    initialize(db_path)
    decision = str(decision or "").strip().upper()
    if decision not in PRICING_APPROVAL_DECISIONS:
        raise ValueError(f"Unsupported pricing approval decision: {decision}")
    decided_by = str(decided_by or "").strip()
    if not decided_by:
        raise ValueError("Pricing approval reviewer is required")
    with commercial_crm.connect(db_path) as conn:
        current = conn.execute(
            """
            SELECT current_revision_number
            FROM commercial_pricing_cases
            WHERE opportunity_id = ? AND pricing_case_id = ?
            """,
            (opportunity_id, pricing_case_id),
        ).fetchone()
        if current is None:
            raise KeyError(f"Unknown pricing case: {pricing_case_id}")
        if int(current["current_revision_number"]) != int(revision_number):
            raise ValueError(
                "Approval decision must reference the current pricing case revision"
            )
        revision = conn.execute(
            """
            SELECT revision_id
            FROM commercial_pricing_case_revisions
            WHERE opportunity_id = ? AND pricing_case_id = ? AND revision_number = ?
            """,
            (opportunity_id, pricing_case_id, revision_number),
        ).fetchone()
        if revision is None:
            raise KeyError(
                f"Unknown pricing case revision: {pricing_case_id}/{revision_number}"
            )
        decided_at = utc_now()
        cursor = conn.execute(
            """
            INSERT INTO commercial_pricing_approvals (
                opportunity_id, pricing_case_id, revision_id, revision_number,
                decision, decided_by, rationale, decided_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opportunity_id,
                pricing_case_id,
                revision["revision_id"],
                revision_number,
                decision,
                decided_by,
                rationale,
                decided_at,
            ),
        )
        commercial_crm._audit(
            conn,
            opportunity_id,
            decided_by,
            "PRICING_APPROVAL",
            f"pricing_case:{pricing_case_id}:revision:{revision_number}",
            None,
            decision,
        )
        approval_id = int(cursor.lastrowid)
        row = conn.execute(
            "SELECT * FROM commercial_pricing_approvals WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()
    return dict(row) if row else {}


def upsert_pricing_case(opportunity_id: str, data: Mapping[str, object], db_path: Path | str = commercial_crm.DB_DEFAULT) -> int:
    initialize(db_path); _ensure_opportunity(opportunity_id, db_path)
    case_name = str(data.get("case_name") or "").strip()
    if not case_name:
        raise ValueError("Pricing case name is required")
    now = utc_now()
    case_id = data.get("pricing_case_id")
    values = (
        case_name,
        data.get("supplier_reference"),
        data.get("supplier_currency"),
        data.get("supplier_cost"),
        data.get("pricing_currency"),
        data.get("fx_rate_to_pricing_currency"),
        data.get("freight_cost"),
        data.get("clearing_and_tax_cost"),
        data.get("financing_cost"),
        data.get("other_costs"),
        data.get("selling_price"),
        1 if str(data.get("cost_basis_complete") or "").lower() in {"1","true","yes","y","on"} else 0,
        data.get("payment_terms"),
        data.get("quote_valid_until"),
        data.get("notes"),
        data.get("created_by"),
    )
    with commercial_crm.connect(db_path) as conn:
        if case_id:
            current = conn.execute(
                """
                SELECT current_revision_number
                FROM commercial_pricing_cases
                WHERE pricing_case_id = ? AND opportunity_id = ?
                """,
                (case_id, opportunity_id),
            ).fetchone()
            if current is None:
                raise KeyError(f"Unknown pricing case: {case_id}")
            revision_number = int(current["current_revision_number"]) + 1
            conn.execute(
                """UPDATE commercial_pricing_cases
                   SET case_name=?, supplier_reference=?, supplier_currency=?, supplier_cost=?,
                       pricing_currency=?, fx_rate_to_pricing_currency=?, freight_cost=?,
                       clearing_and_tax_cost=?, financing_cost=?, other_costs=?, selling_price=?,
                       cost_basis_complete=?, payment_terms=?, quote_valid_until=?, notes=?,
                       created_by=?, current_revision_number=?, updated_at=?
                   WHERE pricing_case_id=? AND opportunity_id=?""",
                values + (revision_number, now, case_id, opportunity_id),
            )
            pricing_case_id = int(case_id)
        else:
            revision_number = 1
            cur = conn.execute(
                """INSERT INTO commercial_pricing_cases(
                       opportunity_id, case_name, supplier_reference, supplier_currency, supplier_cost,
                       pricing_currency, fx_rate_to_pricing_currency, freight_cost, clearing_and_tax_cost,
                       financing_cost, other_costs, selling_price, cost_basis_complete, payment_terms,
                       quote_valid_until, notes, created_by, current_revision_number, created_at, updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (opportunity_id,) + values + (revision_number, now, now),
            )
            pricing_case_id = int(cur.lastrowid)
        revision_fields = ", ".join(PRICING_FIELDS)
        conn.execute(
            f"""
            INSERT INTO commercial_pricing_case_revisions (
                pricing_case_id, opportunity_id, revision_number,
                {revision_fields}, created_at
            )
            SELECT pricing_case_id, opportunity_id, current_revision_number,
                   {revision_fields}, updated_at
            FROM commercial_pricing_cases
            WHERE pricing_case_id = ? AND opportunity_id = ?
            """,
            (pricing_case_id, opportunity_id),
        )
        commercial_crm._audit(
            conn,
            opportunity_id,
            str(data.get("created_by") or "") or None,
            "PRICING_REVISION_CREATED",
            f"pricing_case:{pricing_case_id}",
            None,
            revision_number,
        )
        return pricing_case_id

def get_outcome(opportunity_id: str, db_path: Path | str = commercial_crm.DB_DEFAULT) -> dict[str, object] | None:
    initialize(db_path)
    with commercial_crm.connect(db_path) as conn:
        row = conn.execute("SELECT * FROM opportunity_outcomes WHERE opportunity_id = ?", (opportunity_id,)).fetchone()
    return dict(row) if row else None


def record_outcome(opportunity_id: str, data: Mapping[str, object], db_path: Path | str = commercial_crm.DB_DEFAULT) -> dict[str, object]:
    initialize(db_path); _ensure_opportunity(opportunity_id, db_path)
    outcome = str(data.get("outcome") or "").strip()
    if outcome not in OUTCOME_TYPES: raise ValueError(f"Unsupported outcome: {outcome}")
    with commercial_crm.connect(db_path) as conn:
        conn.execute("""INSERT INTO opportunity_outcomes(opportunity_id,outcome,outcome_date,value,currency,reason,competitor,lessons,recorded_by,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(opportunity_id) DO UPDATE SET outcome=excluded.outcome,outcome_date=excluded.outcome_date,value=excluded.value,currency=excluded.currency,reason=excluded.reason,competitor=excluded.competitor,lessons=excluded.lessons,recorded_by=excluded.recorded_by,recorded_at=excluded.recorded_at""", (opportunity_id,outcome,data.get("outcome_date"),data.get("value"),data.get("currency"),data.get("reason"),data.get("competitor"),data.get("lessons"),data.get("recorded_by"),utc_now()))
    return get_outcome(opportunity_id, db_path) or {}


def snapshot(opportunity_id: str, db_path: Path | str = commercial_crm.DB_DEFAULT) -> dict[str, object]:
    """Return completeness state without recalculating commercial priority."""
    return {"contacts": list_contacts(opportunity_id, db_path), "bid_decision": get_bid_decision(opportunity_id, db_path), "responses": list_responses(opportunity_id, db_path), "evidence": list_evidence(opportunity_id, db_path), "pricing_cases": list_pricing_cases(opportunity_id, db_path), "outcome": get_outcome(opportunity_id, db_path)}
