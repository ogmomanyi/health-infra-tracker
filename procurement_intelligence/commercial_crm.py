"""Persistent CRM state for the commercial execution workspace.

The intelligence pipeline remains the source of truth for opportunity context and
commercial_account_priority_score. This module stores only operational CRM state:
status, ownership, activity overrides, notes, activities, and audit history.

Generated intelligence can be refreshed without destroying CRM work already done.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

DB_DEFAULT = Path("data/commercial_crm.db")
WORKSPACE_DEFAULT = Path("data/commercial_opportunity_workspace.csv")

OPPORTUNITY_STATUSES = (
    "OPEN",
    "QUALIFIED",
    "BID_NO_BID",
    "SUBMITTED",
    "WON",
    "LOST",
    "ON_HOLD",
)

CONTEXT_COLUMNS = (
    "opportunity_id",
    "action_id",
    "target_account_id",
    "account_name",
    "country",
    "account_type",
    "crm_stage",
    "commercial_account_priority_score",
    "commercial_account_priority_tier",
    "action_category",
    "action_status",
    "next_activity",
    "next_activity_due_date",
    "procurement_event_id",
    "tender_reference",
    "title",
    "buyer",
    "procurement_stage",
    "publication_date",
    "closing_date",
    "days_to_closing",
    "estimated_value",
    "currency",
    "equipment_category",
    "product_family",
    "catalogue_fit_status",
    "catalogue_matched_products",
    "source",
    "source_url",
    "priority_reason",
    "recommended_action",
    "familiarity_evidence_ids",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(db_path: Path | str = DB_DEFAULT) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize(db_path: Path | str = DB_DEFAULT) -> None:
    """Create the CRM schema without touching any generated intelligence data."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS opportunity_context (
                opportunity_id TEXT PRIMARY KEY,
                action_id TEXT,
                target_account_id TEXT,
                account_name TEXT,
                country TEXT,
                account_type TEXT,
                crm_stage TEXT,
                commercial_account_priority_score REAL,
                commercial_account_priority_tier TEXT,
                action_category TEXT,
                action_status TEXT,
                next_activity TEXT,
                next_activity_due_date TEXT,
                procurement_event_id TEXT,
                tender_reference TEXT,
                title TEXT,
                buyer TEXT,
                procurement_stage TEXT,
                publication_date TEXT,
                closing_date TEXT,
                days_to_closing INTEGER,
                estimated_value REAL,
                currency TEXT,
                equipment_category TEXT,
                product_family TEXT,
                catalogue_fit_status TEXT,
                catalogue_matched_products TEXT,
                source TEXT,
                source_url TEXT,
                priority_reason TEXT,
                recommended_action TEXT,
                familiarity_evidence_ids TEXT,
                synced_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS opportunity_state (
                opportunity_id TEXT PRIMARY KEY
                    REFERENCES opportunity_context(opportunity_id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'OPEN'
                    CHECK(status IN ('OPEN','QUALIFIED','BID_NO_BID','SUBMITTED','WON','LOST','ON_HOLD')),
                assigned_owner TEXT,
                next_activity_override TEXT,
                next_activity_due_date_override TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activity_log (
                activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
                opportunity_id TEXT NOT NULL
                    REFERENCES opportunity_context(opportunity_id) ON DELETE CASCADE,
                activity_type TEXT NOT NULL,
                subject TEXT NOT NULL,
                notes TEXT,
                activity_date TEXT,
                due_date TEXT,
                owner TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                opportunity_id TEXT NOT NULL
                    REFERENCES opportunity_context(opportunity_id) ON DELETE CASCADE,
                changed_at TEXT NOT NULL,
                actor TEXT,
                change_type TEXT NOT NULL,
                field_name TEXT,
                old_value TEXT,
                new_value TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_context_account
                ON opportunity_context(target_account_id);
            CREATE INDEX IF NOT EXISTS idx_context_closing
                ON opportunity_context(closing_date);
            CREATE INDEX IF NOT EXISTS idx_state_status
                ON opportunity_state(status);
            CREATE INDEX IF NOT EXISTS idx_state_owner
                ON opportunity_state(assigned_owner);
            CREATE INDEX IF NOT EXISTS idx_activity_opportunity
                ON activity_log(opportunity_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_audit_opportunity
                ON audit_log(opportunity_id, changed_at DESC);
            """
        )


def _normalise_row(row: Mapping[str, object]) -> dict[str, object]:
    result = {column: row.get(column, "") for column in CONTEXT_COLUMNS}
    for numeric in ("commercial_account_priority_score", "days_to_closing", "estimated_value"):
        value = result[numeric]
        if value in ("", None):
            result[numeric] = None
        else:
            try:
                result[numeric] = float(value)
            except (TypeError, ValueError):
                result[numeric] = None
    for numeric in ("days_to_closing",):
        value = result[numeric]
        if value is not None:
            result[numeric] = int(value)
    result["opportunity_id"] = str(result["opportunity_id"] or "").strip()
    return result


def sync_opportunities(
    rows: Iterable[Mapping[str, object]],
    db_path: Path | str = DB_DEFAULT,
) -> int:
    """Synchronize canonical opportunity context while preserving CRM state."""
    initialize(db_path)
    count = 0
    synced_at = utc_now()
    with connect(db_path) as conn:
        for raw in rows:
            row = _normalise_row(raw)
            opportunity_id = row["opportunity_id"]
            if not opportunity_id:
                continue
            columns = (*CONTEXT_COLUMNS, "synced_at")
            placeholders = ", ".join("?" for _ in columns)
            updates = ", ".join(
                f"{column}=excluded.{column}" for column in CONTEXT_COLUMNS if column != "opportunity_id"
            )
            values = [row[column] for column in CONTEXT_COLUMNS] + [synced_at]
            conn.execute(
                f"""
                INSERT INTO opportunity_context ({', '.join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(opportunity_id) DO UPDATE SET
                    {updates}, synced_at=excluded.synced_at
                """,
                values,
            )
            now = utc_now()
            conn.execute(
                """
                INSERT INTO opportunity_state (opportunity_id, status, created_at, updated_at)
                VALUES (?, 'OPEN', ?, ?)
                ON CONFLICT(opportunity_id) DO NOTHING
                """,
                (opportunity_id, now, now),
            )
            count += 1
    return count


def load_workspace_csv(path: Path | str = WORKSPACE_DEFAULT) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def get_opportunity(opportunity_id: str, db_path: Path | str = DB_DEFAULT) -> dict[str, object] | None:
    initialize(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT c.*, s.status, s.assigned_owner, s.next_activity_override,
                   s.next_activity_due_date_override, s.notes,
                   s.created_at AS state_created_at, s.updated_at AS state_updated_at
            FROM opportunity_context c
            JOIN opportunity_state s ON s.opportunity_id = c.opportunity_id
            WHERE c.opportunity_id = ?
            """,
            (opportunity_id,),
        ).fetchone()
    return dict(row) if row else None


def list_opportunities(
    db_path: Path | str = DB_DEFAULT,
    status: str | None = None,
    owner: str | None = None,
) -> list[dict[str, object]]:
    initialize(db_path)
    clauses: list[str] = []
    values: list[object] = []
    if status:
        clauses.append("s.status = ?")
        values.append(status)
    if owner:
        clauses.append("s.assigned_owner = ?")
        values.append(owner)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT c.*, s.status, s.assigned_owner, s.next_activity_override,
                   s.next_activity_due_date_override, s.notes,
                   s.created_at AS state_created_at, s.updated_at AS state_updated_at
            FROM opportunity_context c
            JOIN opportunity_state s ON s.opportunity_id = c.opportunity_id
            {where}
            ORDER BY c.commercial_account_priority_score DESC,
                     c.closing_date ASC,
                     c.account_name ASC
            """,
            values,
        ).fetchall()
    return [dict(row) for row in rows]


def _audit(
    conn: sqlite3.Connection,
    opportunity_id: str,
    actor: str | None,
    change_type: str,
    field_name: str | None,
    old_value: object | None,
    new_value: object | None,
) -> None:
    conn.execute(
        """
        INSERT INTO audit_log
            (opportunity_id, changed_at, actor, change_type, field_name, old_value, new_value)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            opportunity_id,
            utc_now(),
            actor,
            change_type,
            field_name,
            None if old_value is None else str(old_value),
            None if new_value is None else str(new_value),
        ),
    )


def update_state(
    opportunity_id: str,
    *,
    db_path: Path | str = DB_DEFAULT,
    actor: str | None = None,
    status: str | None = None,
    assigned_owner: str | None = None,
    next_activity: str | None = None,
    next_activity_due_date: str | None = None,
    notes: str | None = None,
) -> dict[str, object]:
    initialize(db_path)
    if status is not None and status not in OPPORTUNITY_STATUSES:
        raise ValueError(f"Unsupported opportunity status: {status}")

    fields = {
        "status": status,
        "assigned_owner": assigned_owner,
        "next_activity_override": next_activity,
        "next_activity_due_date_override": next_activity_due_date,
        "notes": notes,
    }
    fields = {key: value for key, value in fields.items() if value is not None}
    with connect(db_path) as conn:
        current = conn.execute(
            "SELECT * FROM opportunity_state WHERE opportunity_id = ?",
            (opportunity_id,),
        ).fetchone()
        if current is None:
            raise KeyError(f"Unknown opportunity: {opportunity_id}")
        now = utc_now()
        for field_name, new_value in fields.items():
            old_value = current[field_name]
            if old_value == new_value:
                continue
            conn.execute(
                f"UPDATE opportunity_state SET {field_name} = ?, updated_at = ? WHERE opportunity_id = ?",
                (new_value, now, opportunity_id),
            )
            _audit(conn, opportunity_id, actor, "STATE_CHANGE", field_name, old_value, new_value)
        conn.execute(
            "UPDATE opportunity_state SET updated_at = ? WHERE opportunity_id = ?",
            (now, opportunity_id),
        )
    result = get_opportunity(opportunity_id, db_path)
    assert result is not None
    return result


def add_activity(
    opportunity_id: str,
    activity_type: str,
    subject: str,
    *,
    db_path: Path | str = DB_DEFAULT,
    notes: str | None = None,
    activity_date: str | None = None,
    due_date: str | None = None,
    owner: str | None = None,
    actor: str | None = None,
) -> int:
    initialize(db_path)
    with connect(db_path) as conn:
        exists = conn.execute(
            "SELECT 1 FROM opportunity_context WHERE opportunity_id = ?",
            (opportunity_id,),
        ).fetchone()
        if exists is None:
            raise KeyError(f"Unknown opportunity: {opportunity_id}")
        cur = conn.execute(
            """
            INSERT INTO activity_log
                (opportunity_id, activity_type, subject, notes, activity_date, due_date, owner, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (opportunity_id, activity_type, subject, notes, activity_date, due_date, owner, utc_now()),
        )
        activity_id = int(cur.lastrowid)
        _audit(conn, opportunity_id, actor, "ACTIVITY_ADDED", "activity_id", None, activity_id)
    return activity_id


def list_activities(opportunity_id: str, db_path: Path | str = DB_DEFAULT) -> list[dict[str, object]]:
    initialize(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM activity_log WHERE opportunity_id = ? ORDER BY created_at DESC, activity_id DESC",
            (opportunity_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_audit_log(opportunity_id: str, db_path: Path | str = DB_DEFAULT) -> list[dict[str, object]]:
    initialize(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE opportunity_id = ? ORDER BY changed_at DESC, audit_id DESC",
            (opportunity_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage persistent commercial CRM state")
    parser.add_argument("--db", type=Path, default=DB_DEFAULT)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create the CRM schema")

    sync = sub.add_parser("sync", help="Sync canonical opportunity context from the workspace CSV")
    sync.add_argument("--workspace", type=Path, default=WORKSPACE_DEFAULT)

    state = sub.add_parser("state", help="Update an opportunity's CRM state")
    state.add_argument("opportunity_id")
    state.add_argument("--actor")
    state.add_argument("--status", choices=OPPORTUNITY_STATUSES)
    state.add_argument("--owner")
    state.add_argument("--next-activity")
    state.add_argument("--due-date")
    state.add_argument("--notes")

    activity = sub.add_parser("activity", help="Add an activity to an opportunity")
    activity.add_argument("opportunity_id")
    activity.add_argument("activity_type")
    activity.add_argument("subject")
    activity.add_argument("--notes")
    activity.add_argument("--activity-date")
    activity.add_argument("--due-date")
    activity.add_argument("--owner")
    activity.add_argument("--actor")

    args = parser.parse_args()
    if args.command == "init":
        initialize(args.db)
        print(f"Initialized {args.db}")
    elif args.command == "sync":
        count = sync_opportunities(load_workspace_csv(args.workspace), args.db)
        print(f"Synchronized {count} opportunities into {args.db}")
    elif args.command == "state":
        result = update_state(
            args.opportunity_id,
            db_path=args.db,
            actor=args.actor,
            status=args.status,
            assigned_owner=args.owner,
            next_activity=args.next_activity,
            next_activity_due_date=args.due_date,
            notes=args.notes,
        )
        print(f"Updated {result['opportunity_id']}: {result['status']}")
    elif args.command == "activity":
        activity_id = add_activity(
            args.opportunity_id,
            args.activity_type,
            args.subject,
            db_path=args.db,
            notes=args.notes,
            activity_date=args.activity_date,
            due_date=args.due_date,
            owner=args.owner,
            actor=args.actor,
        )
        print(f"Created activity {activity_id}")


if __name__ == "__main__":
    main()
