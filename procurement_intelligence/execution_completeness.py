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
    return {"contacts": list_contacts(opportunity_id, db_path), "bid_decision": get_bid_decision(opportunity_id, db_path), "responses": list_responses(opportunity_id, db_path), "evidence": list_evidence(opportunity_id, db_path), "outcome": get_outcome(opportunity_id, db_path)}
