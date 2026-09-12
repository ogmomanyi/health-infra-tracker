"""Cache authoritative World Bank project parties for relevant procurement awards."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .http_client import build_session


DEFAULT_URL = "https://search.worldbank.org/api/v2/projects"
FIELDS = [
    "project_reference", "project_name", "borrower", "implementing_agency",
    "country", "source_url", "fetched_at", "fetch_status",
]


def _text(value: object) -> str:
    if isinstance(value, list):
        return "; ".join(str(item).strip() for item in value if str(item).strip())
    return " ".join(str(value or "").split())


def _read(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def relevant_project_references(
    product_matches: Iterable[dict[str, str]],
    events: Iterable[dict[str, str]],
) -> list[str]:
    events_by_id = {
        _text(row.get("procurement_event_id")): row for row in events
    }
    references = set()
    for match in product_matches:
        if not _text(match.get("manufacturer_names")):
            continue
        event = events_by_id.get(_text(match.get("procurement_event_id")), {})
        if _text(event.get("source")) != "World Bank":
            continue
        reference = _text(event.get("project_reference"))
        if reference:
            references.add(reference)
    return sorted(references)


def fetch_project(
    project_reference: str,
    *,
    session=None,
    url: str = DEFAULT_URL,
    timeout: int = 30,
) -> dict[str, Any]:
    client = session or build_session()
    response = client.get(
        url,
        params={
            "format": "json",
            "fl": "id,project_name,borrower,impagency,countryname,url",
            "projectid": project_reference,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    projects = payload.get("projects", {}) if isinstance(payload, dict) else {}
    if isinstance(projects, dict):
        return dict(projects.get(project_reference) or next(iter(projects.values()), {}))
    if isinstance(projects, list):
        return dict(projects[0]) if projects else {}
    return {}


def build_project_metadata(
    project_references: Iterable[str],
    existing_rows: Iterable[dict[str, str]] = (),
    *,
    fetcher: Callable[[str], dict[str, Any]] = fetch_project,
    fetched_at: str | None = None,
) -> list[dict[str, str]]:
    cached = {
        _text(row.get("project_reference")): dict(row)
        for row in existing_rows
        if _text(row.get("project_reference"))
        and _text(row.get("fetch_status")) == "SUCCESS"
    }
    observed_at = fetched_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for reference in sorted({_text(value) for value in project_references if _text(value)}):
        if reference in cached:
            continue
        try:
            project = fetcher(reference)
            if not project:
                raise ValueError("project not returned")
            cached[reference] = {
                "project_reference": reference,
                "project_name": _text(project.get("project_name")),
                "borrower": _text(project.get("borrower")),
                "implementing_agency": _text(project.get("impagency") or project.get("implementing_agency")),
                "country": _text(project.get("countryname") or project.get("country")),
                "source_url": _text(project.get("url")) or f"https://projects.worldbank.org/en/projects-operations/project-detail/{reference}",
                "fetched_at": observed_at,
                "fetch_status": "SUCCESS",
            }
        except Exception:
            cached[reference] = {
                "project_reference": reference,
                "project_name": "", "borrower": "", "implementing_agency": "",
                "country": "", "source_url": "", "fetched_at": observed_at,
                "fetch_status": "FAILED",
            }
    return [cached[key] for key in sorted(cached)]


def write_metadata(path: Path, rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matches", default="data/procurement_product_matches.csv")
    parser.add_argument("--events", default="data/procurement_events.csv")
    parser.add_argument("--output", default="data/world_bank_project_metadata.csv")
    args = parser.parse_args()
    output = Path(args.output)
    references = relevant_project_references(
        _read(Path(args.matches)), _read(Path(args.events))
    )
    rows = build_project_metadata(references, _read(output))
    write_metadata(output, rows)
    successful = sum(row["fetch_status"] == "SUCCESS" for row in rows)
    print(f"World Bank project metadata cached: {successful}/{len(rows)} successful")


if __name__ == "__main__":
    main()
