"""Turn a selected IATI project into durable, actionable CRM work."""

from __future__ import annotations

import csv
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Mapping

from . import commercial_crm


PROJECTS_DEFAULT = Path("data/opportunities.csv")


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _number(value: object) -> float | None:
    try:
        return float(value) if _text(value) else None
    except (TypeError, ValueError):
        return None


def _first(value: object) -> str:
    return next((item.strip() for item in _text(value).split(";") if item.strip()), "")


def _stable_id(prefix: str, value: str) -> str:
    return prefix + sha256(value.encode("utf-8")).hexdigest()[:20]


def opportunity_id(project_id: str) -> str:
    return _stable_id("project_", project_id)


def _load(path: Path | str) -> list[dict[str, str]]:
    source = Path(path)
    if not source.exists():
        return []
    with source.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _score(row: Mapping[str, object]) -> float:
    return _number(row.get("opportunity_score")) or 0.0


def _tier(score: float) -> str:
    if score >= 85:
        return "ACT_NOW"
    if score >= 65:
        return "PRIORITISE"
    return "DEVELOP"


def _days_to(value: str) -> int | None:
    if not value:
        return None
    try:
        return (date.fromisoformat(value) - date.today()).days
    except ValueError:
        return None


def project_context(project: Mapping[str, object]) -> dict[str, object]:
    project_id = _text(project.get("iati_identifier"))
    if not project_id:
        raise ValueError("Project has no IATI identifier")
    score = _score(project)
    account_name = (
        _first(project.get("implementing_partners"))
        or _first(project.get("reporting_org_name"))
        or _first(project.get("funding_agencies"))
        or "Project account"
    )
    country = _first(project.get("country_names")) or _first(project.get("country_codes"))
    closing_date = _text(project.get("next_disbursement_date") or project.get("next_budget_date"))
    estimated_value = next((
        value for value in (
            _number(project.get("future_disbursement_usd")),
            _number(project.get("future_budget_usd")),
            _number(project.get("budget_usd")),
        ) if value is not None and value > 0
    ), None)
    recommended = _text(project.get("recommended_action") or project.get("recommended_procurement_action"))
    return {
        "opportunity_id": opportunity_id(project_id),
        "action_id": _stable_id("project_selection_", project_id),
        "target_account_id": _stable_id("project_account_", f"{account_name}|{country}"),
        "account_name": account_name,
        "country": country,
        "account_type": "PROJECT",
        "crm_stage": _text(project.get("activity_status_label")),
        "commercial_account_priority_score": score,
        "commercial_account_priority_tier": _tier(score),
        "action_category": "PROJECT_FOLLOW_UP",
        "action_status": "SELECTED",
        "next_activity": recommended or "Qualify the project, buyer and procurement route.",
        "next_activity_due_date": "",
        "procurement_event_id": "",
        "tender_reference": project_id,
        "title": _text(project.get("project_title")) or project_id,
        "buyer": _text(project.get("implementing_partners")),
        "procurement_stage": _text(project.get("tender_stage")),
        "publication_date": _text(project.get("last_updated")),
        "closing_date": closing_date,
        "days_to_closing": _days_to(closing_date),
        "estimated_value": estimated_value,
        "currency": "USD" if estimated_value is not None else "",
        "equipment_category": _text(project.get("equipment_target_summary")),
        "product_family": _text(project.get("direct_equipment_categories")),
        "catalogue_fit_status": "",
        "catalogue_matched_products": "",
        "source": "IATI",
        "source_url": "",
        "priority_reason": _text(project.get("signal_summary")),
        "recommended_action": recommended,
        "familiarity_evidence_ids": f"IATI:{project_id}",
    }


def list_projects(
    *,
    projects_path: Path | str = PROJECTS_DEFAULT,
    db_path: Path | str = commercial_crm.DB_DEFAULT,
    query: str | None = None,
    country: str | None = None,
    priority: str | None = None,
    tracked: bool | None = None,
    limit: int = 500,
) -> dict[str, object]:
    tracked_rows = {row["project_id"]: row for row in commercial_crm.list_tracked_projects(db_path)}
    query_value = _text(query).casefold()
    country_value = _text(country).casefold()
    priority_value = _text(priority).casefold()
    projects: list[dict[str, object]] = []
    for raw in _load(projects_path):
        project_id = _text(raw.get("iati_identifier"))
        tracking = tracked_rows.get(project_id)
        if tracked is not None and bool(tracking) != tracked:
            continue
        haystack = " ".join(_text(raw.get(field)) for field in (
            "iati_identifier", "project_title", "reporting_org_name", "funding_agencies",
            "implementing_partners", "country_codes", "country_names", "equipment_target_summary",
            "signal_summary", "description",
        )).casefold()
        if query_value and query_value not in haystack:
            continue
        countries = f"{_text(raw.get('country_names'))};{_text(raw.get('country_codes'))}".casefold()
        if country_value and country_value not in countries:
            continue
        if priority_value and _text(raw.get("priority_band")).casefold() != priority_value:
            continue
        item: dict[str, object] = dict(raw)
        item["project_id"] = project_id
        item["tracked"] = bool(tracking)
        if tracking:
            item.update({
                "opportunity_id": tracking.get("opportunity_id"),
                "workflow_status": tracking.get("status"),
                "assigned_owner": tracking.get("assigned_owner"),
                "workflow_next_activity": tracking.get("next_activity_override") or tracking.get("next_activity"),
                "workflow_due_date": tracking.get("next_activity_due_date_override") or tracking.get("next_activity_due_date"),
                "selected_at": tracking.get("selected_at"),
                "selected_by": tracking.get("selected_by"),
                "selection_reason": tracking.get("selection_reason"),
            })
        projects.append(item)
    projects.sort(key=lambda row: (
        not bool(row.get("tracked")), -_score(row), _text(row.get("project_title")).casefold(),
    ))
    total = len(projects)
    limit = max(1, min(int(limit), 2000))
    return {
        "summary": {"matching": total, "returned": min(total, limit), "tracked": len(tracked_rows)},
        "projects": projects[:limit],
    }


def track_project(
    project_id: str,
    *,
    projects_path: Path | str = PROJECTS_DEFAULT,
    db_path: Path | str = commercial_crm.DB_DEFAULT,
    owner: str | None = None,
    next_activity: str | None = None,
    due_date: str | None = None,
    selection_reason: str | None = None,
    selected_by: str | None = None,
) -> dict[str, object]:
    project = next((row for row in _load(projects_path) if _text(row.get("iati_identifier")) == _text(project_id)), None)
    if project is None:
        raise KeyError(f"Unknown project: {project_id}")
    context = project_context(project)
    commercial_crm.sync_opportunities([context], db_path)
    tracking = commercial_crm.track_project(
        _text(project_id), str(context["opportunity_id"]), db_path=db_path,
        selected_by=selected_by, selection_reason=selection_reason,
    )
    action = _text(next_activity) or _text(context["next_activity"])
    due = _text(due_date) or (date.today() + timedelta(days=7)).isoformat()
    opportunity = commercial_crm.update_state(
        str(context["opportunity_id"]), db_path=db_path, actor=selected_by,
        assigned_owner=_text(owner), next_activity=action, next_activity_due_date=due,
    )
    if tracking["created"]:
        commercial_crm.add_activity(
            str(context["opportunity_id"]), "PROJECT_SELECTED", "Project selected for follow-up",
            db_path=db_path, notes=_text(selection_reason) or _text(project.get("signal_summary")),
            due_date=due, owner=_text(owner), actor=selected_by,
        )
    return {"tracked_project": tracking, "opportunity": opportunity}
