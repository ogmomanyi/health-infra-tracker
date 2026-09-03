"""Build matcher candidates from the authoritative normalized IATI activities table."""

from __future__ import annotations

import sqlite3
from pathlib import Path


COUNTRY_NAMES = {
    "KE": "Kenya",
    "UG": "Uganda",
    "RW": "Rwanda",
    "ET": "Ethiopia",
    "SO": "Somalia",
    "SS": "South Sudan",
    "CD": "Congo, Democratic Republic of the",
    "TZ": "Tanzania",
}

CANDIDATE_FIELDS = (
    "iati_identifier", "project_title", "activity_title", "project_name",
    "programme_title", "country_codes", "country_names", "reporting_org_name",
    "funding_agencies", "implementing_partners", "implementing_agencies",
    "implementing_agency", "equipment_target_summary", "equipment_target_categories",
    "product_family", "project_reference", "project_id", "reference", "activity_ref",
    "external_project_id", "programme_reference",
)


def load_iati_candidates(database: Path) -> list[dict[str, str]]:
    """Return matcher-ready candidates from the normalized activities table.

    The column list is discovered at runtime so older database snapshots remain
    usable as long as the core IATI fields exist.
    """
    if not database.exists():
        return []

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "activities" not in tables:
            return []

        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(activities)")
        }
        selected = [field for field in CANDIDATE_FIELDS if field in columns]
        if "iati_identifier" not in selected:
            return []

        sql = "SELECT " + ", ".join(f'"{field}"' for field in selected) + " FROM activities"
        rows = connection.execute(sql).fetchall()

    index = {field: position for position, field in enumerate(selected)}
    candidates: list[dict[str, str]] = []
    for row in rows:
        candidate = {
            field: str(row[index[field]] or "") if field in index else ""
            for field in CANDIDATE_FIELDS
        }
        country_codes = candidate.get("country_codes", "")
        if not candidate.get("country_names") and country_codes:
            codes = [code.strip().upper() for code in country_codes.replace(";", ",").split(",")]
            candidate["country_names"] = "; ".join(
                COUNTRY_NAMES.get(code, code) for code in codes if code
            )
        candidates.append(candidate)
    return candidates
