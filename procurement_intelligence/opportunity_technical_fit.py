"""Read-only bridge from generated tender product-fit intelligence to the CRM API."""
from __future__ import annotations

import csv
from pathlib import Path

DEFAULT_PATH = Path("data/faram_product_fit.csv")


def load_product_fit(path: Path | str = DEFAULT_PATH) -> list[dict[str, str]]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def for_event(event_id: object, path: Path | str = DEFAULT_PATH) -> list[dict[str, str]]:
    target = str(event_id or "").strip()
    if not target:
        return []
    return [row for row in load_product_fit(path) if str(row.get("procurement_event_id") or "").strip() == target]
