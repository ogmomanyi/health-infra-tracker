"""Load and match explicit Faram commercial channel constraints.

Channel constraints are controlled evidence. They do not establish Faram principal
status and they never mutate CRM state or canonical commercial priority.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterable, Mapping

DEFAULT_PATH = Path("data/faram_channel_constraints.csv")

_COUNTRY_ALIASES = {
    "ke": "kenya",
    "kenya": "kenya",
    "ug": "uganda",
    "uganda": "uganda",
    "rw": "rwanda",
    "rwanda": "rwanda",
    "et": "ethiopia",
    "ethiopia": "ethiopia",
    "so": "somalia",
    "somalia": "somalia",
    "ss": "south sudan",
    "south sudan": "south sudan",
    "cd": "drc",
    "drc": "drc",
    "democratic republic of the congo": "drc",
    "democratic republic of congo": "drc",
}


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _normalize(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _text(value).lower()).strip()


def _country(value: object) -> str:
    normalized = _normalize(value)
    return _COUNTRY_ALIASES.get(normalized, normalized)


def load(path: Path | str = DEFAULT_PATH) -> list[dict[str, str]]:
    source = Path(path)
    if not source.is_file():
        return []
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def match(
    opportunity: Mapping[str, object],
    technical_fit: Iterable[Mapping[str, object]],
    constraints: Iterable[Mapping[str, object]],
) -> list[dict[str, str]]:
    """Return explicit constraints relevant to candidate manufacturers and country."""
    country = _country(opportunity.get("country"))
    manufacturers = {
        _normalize(row.get("manufacturer_name"))
        for row in technical_fit
        if _normalize(row.get("manufacturer_name"))
    }
    if not country or not manufacturers:
        return []

    matched: list[dict[str, str]] = []
    for raw in constraints:
        manufacturer = _normalize(raw.get("manufacturer_name"))
        constraint_country = _country(raw.get("country"))
        if manufacturer not in manufacturers or constraint_country != country:
            continue
        matched.append({key: _text(value) for key, value in raw.items()})
    return matched
