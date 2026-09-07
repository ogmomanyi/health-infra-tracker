"""Aggregate explicit manufacturer/brand evidence from procurement awards.

Manufacturer attribution is evidence-led. A supplier name is never treated as
a manufacturer, and an empty Faram catalogue is reported as unknown coverage
rather than as proof that Faram lacks a principal.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from .schema import ProcurementEvent

FIELDS = [
    "manufacturer_name", "brand_name", "evidence_status", "award_count",
    "suppliers", "buyers", "countries", "categories", "projects",
    "latest_evidence_date", "source_urls", "tender_references",
    "faram_catalogue_status", "faram_products", "competitive_gap",
    "recommended_action",
]


def _norm(value: object) -> str:
    text = " ".join(str(value or "").lower().split())
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _join(values: set[str]) -> str:
    return "; ".join(sorted(value for value in values if value))


def _catalogue_manufacturers(path: Path) -> dict[str, set[str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        result: dict[str, set[str]] = {}
        for row in csv.DictReader(handle):
            manufacturer = " ".join((row.get("manufacturer_name") or "").split())
            if not manufacturer:
                continue
            result.setdefault(_norm(manufacturer), set()).add(" ".join((row.get("product_name") or "").split()))
        return result


def build_manufacturer_history(events: list[ProcurementEvent], catalogue_path: Path | None = None) -> list[dict[str, str]]:
    groups: dict[tuple[str, str], dict[str, object]] = {}
    for event in events:
        if event.manufacturer_evidence_status != "EXPLICIT":
            continue
        manufacturer = " ".join(event.manufacturer_name.split())
        brand = " ".join(event.brand_name.split())
        key = (_norm(manufacturer), _norm(brand))
        if not key[0] and not key[1]:
            continue
        group = groups.setdefault(key, {
            "manufacturer_name": manufacturer,
            "brand_name": brand,
            "evidence_status": "EXPLICIT",
            "award_count": 0,
            "suppliers": set(), "buyers": set(), "countries": set(), "categories": set(),
            "projects": set(), "dates": [], "source_urls": set(), "tender_references": set(),
        })
        group["award_count"] += 1
        group["suppliers"].add(event.supplier_canonical_name or event.supplier_name)
        group["buyers"].add(event.buyer)
        group["countries"].add(event.country)
        group["categories"].add(event.equipment_category)
        group["projects"].add(event.matched_iati_identifier or event.project_reference)
        group["source_urls"].add(event.source_url)
        group["tender_references"].add(event.tender_reference)
        if event.publication_date:
            group["dates"].append(event.publication_date)

    catalogue = _catalogue_manufacturers(catalogue_path) if catalogue_path else {}
    rows: list[dict[str, str]] = []
    for group in groups.values():
        manufacturer = str(group["manufacturer_name"])
        match_key = _norm(manufacturer)
        products = sorted(product for product in catalogue.get(match_key, set()) if product)
        if catalogue_path and catalogue:
            if match_key and match_key in catalogue:
                catalogue_status = "FARAM_CATALOGUE_MATCH"
                gap = "EXISTING_PRINCIPAL_COVERAGE"
                action = "Review incumbent supplier, tender specifications, pricing and Faram principal relationship."
            else:
                catalogue_status = "NO_FARAM_MANUFACTURER_MATCH"
                gap = "PRINCIPAL_ACQUISITION_CANDIDATE"
                action = "Investigate manufacturer/principal acquisition, then validate territory, product fit and authorization."
        else:
            catalogue_status = "CATALOGUE_NOT_POPULATED"
            gap = "UNKNOWN_COVERAGE"
            action = "Populate and validate the controlled Faram catalogue before concluding whether a principal acquisition is required."
        rows.append({
            "manufacturer_name": manufacturer,
            "brand_name": str(group["brand_name"]),
            "evidence_status": "EXPLICIT",
            "award_count": str(group["award_count"]),
            "suppliers": _join(group["suppliers"]), "buyers": _join(group["buyers"]),
            "countries": _join(group["countries"]), "categories": _join(group["categories"]),
            "projects": _join(group["projects"]),
            "latest_evidence_date": max(group["dates"]) if group["dates"] else "",
            "source_urls": _join(group["source_urls"]),
            "tender_references": _join(group["tender_references"]),
            "faram_catalogue_status": catalogue_status, "faram_products": "; ".join(products),
            "competitive_gap": gap, "recommended_action": action,
        })
    return sorted(rows, key=lambda row: (-int(row["award_count"]), row["manufacturer_name"], row["brand_name"]))


def write_manufacturer_history(path: Path, events: list[ProcurementEvent], catalogue_path: Path | None = None) -> int:
    rows = build_manufacturer_history(events, catalogue_path=catalogue_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
