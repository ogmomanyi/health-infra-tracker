"""Build evidence-led product and manufacturer intelligence datasets.

The controlled Faram catalogue is authoritative for current product, principal,
and territory status. Historical quotations, IATI text, and procurement records
add market evidence without creating or activating a principal relationship.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd


ACTIVE_PRINCIPAL_STATUSES = {"active", "approved", "current"}
PENDING_PRINCIPAL_STATUSES = {"pending", "prospect", "unknown", ""}

MANUFACTURER_ALIASES = {
    "thermo scientific": "Thermo Fisher",
    "thermo fisher scientific": "Thermo Fisher",
    "thermo fisher": "Thermo Fisher",
    "biorad": "Bio-Rad",
    "bio rad": "Bio-Rad",
    "b braun": "B. Braun",
    "bbraun": "B. Braun",
    "ge healthcare": "GE HealthCare",
    "ge health care": "GE HealthCare",
    "siemens healthcare": "Siemens Healthineers",
}

COUNTRY_CODES = {
    "kenya": "KE",
    "uganda": "UG",
    "rwanda": "RW",
    "ethiopia": "ET",
    "somalia": "SO",
    "south sudan": "SS",
    "tanzania": "TZ",
    "democratic republic of the congo": "CD",
    "drc": "CD",
}

PRODUCT_COLUMNS = [
    "product_intelligence_id",
    "faram_product_id",
    "product_name",
    "manufacturer_entity_id",
    "manufacturer_name",
    "product_family",
    "equipment_category",
    "market_equipment_category",
    "model",
    "principal_status",
    "territory",
    "territory_codes",
    "catalogue_status",
    "catalogue_source",
    "historical_quote_count",
    "historical_evidence_strength",
    "family_demand_count",
    "procurement_match_count",
    "actionable_match_count",
    "average_match_confidence",
    "technical_pass_count",
    "technical_review_count",
    "technical_fail_count",
    "technical_unknown_count",
    "evidence_sources",
    "commercial_position",
    "product_intelligence_score",
    "recommended_action",
    "source_layer",
]

MANUFACTURER_ENTITY_COLUMNS = [
    "manufacturer_entity_id",
    "manufacturer_name",
    "manufacturer_aliases",
    "equipment_categories",
    "evidence_source",
    "evidence_sources",
    "activity_count",
    "catalogue_product_count",
    "historical_product_count",
    "historical_quote_count",
    "procurement_award_count",
    "principal_statuses",
    "territories",
    "country_codes",
    "top_countries",
    "latest_evidence_date",
    "source_layer",
]

MANUFACTURER_INTELLIGENCE_COLUMNS = [
    "manufacturer_intelligence_id",
    "manufacturer_entity_id",
    "manufacturer_name",
    "manufacturer_aliases",
    "coverage_status",
    "commercial_priority",
    "commercial_score",
    "catalogue_product_count",
    "active_product_count",
    "pending_product_count",
    "historical_product_count",
    "historical_quote_count",
    "procurement_award_count",
    "explicit_demand_count",
    "aligned_market_demand_count",
    "actionable_match_count",
    "technical_pass_count",
    "technical_review_count",
    "technical_fail_count",
    "technical_unknown_count",
    "product_families",
    "equipment_categories",
    "product_names",
    "models",
    "principal_statuses",
    "territories",
    "country_codes",
    "top_countries",
    "buyers",
    "suppliers",
    "latest_evidence_date",
    "evidence_sources",
    "recommended_action",
    "source_layer",
]

OUTPUT_NAMES = (
    "manufacturer_entities",
    "product_intelligence",
    "manufacturer_intelligence",
)


def _text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return " ".join(str(value).split())


def _normalize(value: object) -> str:
    text = _text(value).casefold().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _stable_id(prefix: str, *parts: object) -> str:
    value = "|".join(_normalize(part) for part in parts if _text(part))
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def _rows(frame: pd.DataFrame | None) -> list[dict[str, object]]:
    if frame is None or frame.empty:
        return []
    return frame.fillna("").to_dict("records")


def _split(value: object) -> list[str]:
    return [
        _text(item)
        for item in re.split(r"[;|\n]+", _text(value))
        if _text(item)
    ]


def _join(values: Iterable[object], limit: int | None = None) -> str:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _text(value)
        key = _normalize(cleaned)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(cleaned)
    output.sort(key=str.casefold)
    if limit is not None:
        output = output[:limit]
    return "; ".join(output)


def _number(value: object) -> float:
    try:
        return float(_text(value) or 0)
    except (TypeError, ValueError):
        return 0.0


def _integer(value: object) -> int:
    return int(round(_number(value)))


def canonical_manufacturer(value: object) -> str:
    name = _text(value)
    return MANUFACTURER_ALIASES.get(_normalize(name), name)


def manufacturer_key(value: object) -> str:
    return _normalize(canonical_manufacturer(value))


def manufacturer_entity_id(value: object) -> str:
    key = manufacturer_key(value)
    return _stable_id("mfr", key) if key else ""


def territory_codes(value: object) -> str:
    codes = []
    for territory in _split(value.replace(",", ";") if isinstance(value, str) else value):
        normalized = _normalize(territory)
        if normalized in {"all", "all countries", "global", "worldwide", "any"}:
            codes.append("GLOBAL")
        elif normalized in COUNTRY_CODES:
            codes.append(COUNTRY_CODES[normalized])
        elif len(normalized) == 2:
            codes.append(normalized.upper())
    return _join(codes)


def market_equipment_category(*values: object) -> str:
    text = " ".join(_normalize(value) for value in values)
    rules = [
        ("PPE", ("personal protective", "ppe", "coverall", "protective product")),
        ("Cold Chain / Storage", ("cold chain", "refrigerator", "freezer", "cold storage")),
        ("Oxygen & Respiratory", ("oxygen", "ventilator", "respiratory")),
        ("Imaging", ("x ray", "ultrasound", "imaging", "radiology")),
        ("Diagnostic Equipment", ("analyzer", "analyser", "diagnostic", "cytology", "pathology")),
        (
            "Laboratory Systems",
            (
                "laboratory", "microplate", "spectro", "incubator", "oven", "balance",
                "ph meter", "microscope", "centrifuge", "filtration", "stirrer", "vortex",
                "colony counter", "water bath", "thermoreactor", "safety cabinet", "pipette",
            ),
        ),
        ("Medical Devices & Equipment", ("medical device", "autoclave", "sterilizer", "steriliser")),
    ]
    for category, phrases in rules:
        if any(phrase in text for phrase in phrases):
            return category
    return "Medical Devices & Equipment" if text else ""


def _manufacturer_bucket(name: object) -> dict[str, object]:
    canonical = canonical_manufacturer(name)
    return {
        "manufacturer_name": canonical,
        "aliases": {canonical, _text(name)},
        "equipment": set(),
        "sources": set(),
        "activities": set(),
        "catalogue_products": set(),
        "historical_products": set(),
        "historical_quotes": 0,
        "awards": 0,
        "statuses": set(),
        "territories": set(),
        "country_codes": set(),
        "countries": set(),
        "dates": set(),
    }


def build_manufacturer_entities_dataset(
    opportunities: pd.DataFrame,
    catalogue: pd.DataFrame | None = None,
    historical_quotes: pd.DataFrame | None = None,
    manufacturer_history: pd.DataFrame | None = None,
    procurement_matches: pd.DataFrame | None = None,
) -> pd.DataFrame:
    groups: dict[str, dict[str, object]] = {}

    def group_for(name: object) -> dict[str, object] | None:
        key = manufacturer_key(name)
        if not key:
            return None
        group = groups.setdefault(key, _manufacturer_bucket(name))
        group["aliases"].add(_text(name))
        return group

    for row in _rows(opportunities):
        for name in _split(row.get("manufacturer_mentions")):
            group = group_for(name)
            if not group:
                continue
            group["sources"].add("IATI activity text mention")
            group["activities"].add(_text(row.get("iati_identifier")))
            group["equipment"].update(_split(row.get("equipment_target_summary")))
            group["country_codes"].update(_split(row.get("country_codes")))

    for row in _rows(catalogue):
        group = group_for(row.get("manufacturer_name"))
        if not group:
            continue
        group["sources"].add("Controlled Faram catalogue")
        group["catalogue_products"].add(_text(row.get("faram_product_id")) or _text(row.get("product_name")))
        group["equipment"].add(market_equipment_category(row.get("product_family"), row.get("equipment_category")))
        group["statuses"].add(_text(row.get("principal_status")) or "unknown")
        group["territories"].update(_split(row.get("territory")))
        group["country_codes"].update(_split(territory_codes(row.get("territory"))))

    for row in _rows(historical_quotes):
        group = group_for(row.get("manufacturer_name"))
        if not group:
            continue
        group["sources"].add("Historical quotation evidence")
        product_key = _text(row.get("product_name")) or _text(row.get("model")) or _text(row.get("product_family"))
        group["historical_products"].add(product_key)
        group["historical_quotes"] += _integer(row.get("historical_quote_count"))
        group["equipment"].add(market_equipment_category(row.get("product_family"), row.get("product_name")))

    for row in _rows(manufacturer_history):
        group = group_for(row.get("manufacturer_name") or row.get("brand_name"))
        if not group:
            continue
        group["sources"].add("Explicit procurement award evidence")
        group["awards"] += _integer(row.get("award_count"))
        group["equipment"].update(_split(row.get("categories")))
        group["countries"].update(_split(row.get("countries")))
        group["country_codes"].update(_split(territory_codes(row.get("countries"))))
        if _text(row.get("latest_evidence_date")):
            group["dates"].add(_text(row.get("latest_evidence_date")))

    for row in _rows(procurement_matches):
        for name in _split(row.get("manufacturer_names")):
            group = group_for(name)
            if not group:
                continue
            group["sources"].add("Explicit procurement notice mention")
            group["equipment"].add(_text(row.get("procurement_category")))
            group["countries"].add(_text(row.get("country")))
            group["country_codes"].update(_split(territory_codes(row.get("country"))))

    output = []
    for group in groups.values():
        name = group["manufacturer_name"]
        output.append({
            "manufacturer_entity_id": manufacturer_entity_id(name),
            "manufacturer_name": name,
            "manufacturer_aliases": _join(group["aliases"]),
            "equipment_categories": _join(group["equipment"]),
            "evidence_source": _join(group["sources"]),
            "evidence_sources": _join(group["sources"]),
            "activity_count": len({value for value in group["activities"] if value}),
            "catalogue_product_count": len({value for value in group["catalogue_products"] if value}),
            "historical_product_count": len({value for value in group["historical_products"] if value}),
            "historical_quote_count": group["historical_quotes"],
            "procurement_award_count": group["awards"],
            "principal_statuses": _join(group["statuses"]),
            "territories": _join(group["territories"]),
            "country_codes": _join(group["country_codes"]),
            "top_countries": _join(group["countries"] or group["country_codes"], limit=8),
            "latest_evidence_date": max(group["dates"]) if group["dates"] else "",
            "source_layer": "canonical",
        })

    if not output:
        return pd.DataFrame(columns=MANUFACTURER_ENTITY_COLUMNS)
    return (
        pd.DataFrame(output, columns=MANUFACTURER_ENTITY_COLUMNS)
        .sort_values(
            by=["catalogue_product_count", "historical_quote_count", "activity_count", "manufacturer_name"],
            ascending=[False, False, False, True],
        )
        .reset_index(drop=True)
    )


def _history_matches(catalogue_row: dict[str, object], history_row: dict[str, object]) -> bool:
    if manufacturer_key(catalogue_row.get("manufacturer_name")) != manufacturer_key(history_row.get("manufacturer_name")):
        return False
    catalogue_model = _normalize(catalogue_row.get("model"))
    history_model = _normalize(history_row.get("model"))
    if catalogue_model and history_model and catalogue_model == history_model:
        return True
    catalogue_product = _normalize(catalogue_row.get("product_name"))
    history_product = _normalize(history_row.get("product_name"))
    return bool(catalogue_product and history_product and catalogue_product == history_product)


def _commercial_position(catalogue_status: str, principal_status: str, actionable_matches: int) -> str:
    normalized = _normalize(principal_status)
    if catalogue_status == "HISTORICAL_ONLY":
        return "HISTORICAL_EVIDENCE_ONLY"
    if normalized in ACTIVE_PRINCIPAL_STATUSES and actionable_matches:
        return "ACTIVE_TENDER_MATCH"
    if normalized in ACTIVE_PRINCIPAL_STATUSES:
        return "ACTIVE_CATALOGUE"
    if normalized == "inactive":
        return "INACTIVE_CATALOGUE"
    return "PRINCIPAL_VALIDATION_REQUIRED"


def _product_action(position: str, technical_failures: int, technical_unknown: int) -> str:
    if technical_failures:
        return "Resolve the verified technical failure before any bid commitment."
    if position == "ACTIVE_TENDER_MATCH" and technical_unknown:
        return "Obtain and verify the missing tender and product specifications before bid approval."
    if position == "ACTIVE_TENDER_MATCH":
        return "Review pricing, compliance, stock, and bid strategy with the principal."
    if position == "ACTIVE_CATALOGUE":
        return "Monitor aligned demand and validate tender-specific technical fit when a notice appears."
    if position == "PRINCIPAL_VALIDATION_REQUIRED":
        return "Confirm current principal authorization and territory before treating this product as actionable."
    if position == "INACTIVE_CATALOGUE":
        return "Keep for reference; do not pursue until principal status is reactivated and verified."
    return "Validate the current manufacturer relationship and territory before adding this historical product to the controlled catalogue."


def build_product_intelligence_dataset(
    catalogue: pd.DataFrame | None,
    historical_quotes: pd.DataFrame | None,
    procurement_matches: pd.DataFrame | None,
    faram_matches: pd.DataFrame | None,
    product_fit: pd.DataFrame | None,
) -> pd.DataFrame:
    catalogue_rows = _rows(catalogue)
    history_rows = _rows(historical_quotes)
    demand_rows = _rows(procurement_matches)
    faram_rows = _rows(faram_matches)
    fit_rows = _rows(product_fit)

    demand_by_family: dict[str, set[str]] = defaultdict(set)
    for row in demand_rows:
        family = _normalize(row.get("product_family"))
        event_id = _text(row.get("procurement_event_id"))
        if family and event_id and _text(row.get("match_status")) != "UNMATCHED":
            demand_by_family[family].add(event_id)

    matches_by_product: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in faram_rows:
        if _text(row.get("faram_product_id")):
            matches_by_product[_text(row.get("faram_product_id"))].append(row)

    fit_by_product: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in fit_rows:
        if _text(row.get("faram_product_id")):
            fit_by_product[_text(row.get("faram_product_id"))].append(row)

    used_history: set[int] = set()
    output: list[dict[str, object]] = []

    for catalogue_row in catalogue_rows:
        histories = []
        for index, history_row in enumerate(history_rows):
            if _history_matches(catalogue_row, history_row):
                histories.append(history_row)
                used_history.add(index)
        output.append(_product_row(
            catalogue_row,
            histories,
            demand_by_family,
            matches_by_product,
            fit_by_product,
            catalogue_status="CONTROLLED_CATALOGUE",
        ))

    for index, history_row in enumerate(history_rows):
        if index in used_history:
            continue
        output.append(_product_row(
            history_row,
            [history_row],
            demand_by_family,
            matches_by_product,
            fit_by_product,
            catalogue_status="HISTORICAL_ONLY",
        ))

    if not output:
        return pd.DataFrame(columns=PRODUCT_COLUMNS)
    return (
        pd.DataFrame(output, columns=PRODUCT_COLUMNS)
        .sort_values(
            by=["product_intelligence_score", "family_demand_count", "product_name"],
            ascending=[False, False, True],
        )
        .reset_index(drop=True)
    )


def _product_row(
    source: dict[str, object],
    histories: list[dict[str, object]],
    demand_by_family: dict[str, set[str]],
    matches_by_product: dict[str, list[dict[str, object]]],
    fit_by_product: dict[str, list[dict[str, object]]],
    catalogue_status: str,
) -> dict[str, object]:
    product_id = _text(source.get("faram_product_id"))
    product_name = _text(source.get("product_name")) or _text(source.get("product_family"))
    manufacturer = canonical_manufacturer(source.get("manufacturer_name"))
    family = _text(source.get("product_family"))
    category = _text(source.get("equipment_category"))
    model = _text(source.get("model"))
    status = _text(source.get("principal_status")) if catalogue_status == "CONTROLLED_CATALOGUE" else "historical"
    territory = _text(source.get("territory"))
    matches = matches_by_product.get(product_id, []) if product_id else []
    fits = fit_by_product.get(product_id, []) if product_id else []
    quote_count = sum(_integer(row.get("historical_quote_count")) for row in histories)
    evidence_strengths = [_text(row.get("evidence_strength")) for row in histories if _text(row.get("evidence_strength"))]
    family_demand = len(demand_by_family.get(_normalize(family), set()))
    actionable = sum(_text(row.get("match_status")) == "FARAM_MATCH" for row in matches)
    technical_pass = sum(_text(row.get("technical_status")) == "PASS" for row in fits)
    technical_review = sum(_text(row.get("technical_status")) == "REVIEW" for row in fits)
    technical_fail = sum(_text(row.get("technical_status")) == "FAIL" for row in fits)
    technical_unknown = sum(_text(row.get("technical_status")) == "UNKNOWN" for row in fits)
    position = _commercial_position(catalogue_status, status, actionable)
    evidence_sources = {"Historical quotation evidence"} if histories else set()
    if catalogue_status == "CONTROLLED_CATALOGUE":
        evidence_sources.add("Controlled Faram catalogue")
    if family_demand:
        evidence_sources.add("External procurement family demand")
    if matches:
        evidence_sources.add("Tender product matching")
    if fits:
        evidence_sources.add("Tender technical fit")

    score = 0.0
    if catalogue_status == "CONTROLLED_CATALOGUE":
        score += 35
    if _normalize(status) in ACTIVE_PRINCIPAL_STATUSES:
        score += 25
    score += min(15, quote_count * 4)
    score += min(10, family_demand * 2)
    score += min(10, actionable * 5)
    score += min(5, technical_pass * 5)
    score -= min(15, technical_fail * 10)

    confidence_values = [_number(row.get("match_confidence")) for row in matches if _text(row.get("match_confidence"))]
    identifier = product_id or _stable_id("historical_product", manufacturer, product_name, model)

    return {
        "product_intelligence_id": _stable_id("product_intel", identifier),
        "faram_product_id": product_id,
        "product_name": product_name,
        "manufacturer_entity_id": manufacturer_entity_id(manufacturer),
        "manufacturer_name": manufacturer,
        "product_family": family,
        "equipment_category": category,
        "market_equipment_category": market_equipment_category(family, category, product_name),
        "model": model,
        "principal_status": status,
        "territory": territory,
        "territory_codes": territory_codes(territory),
        "catalogue_status": catalogue_status,
        "catalogue_source": _text(source.get("source")),
        "historical_quote_count": quote_count,
        "historical_evidence_strength": _join(evidence_strengths),
        "family_demand_count": family_demand,
        "procurement_match_count": len(matches),
        "actionable_match_count": actionable,
        "average_match_confidence": round(sum(confidence_values) / len(confidence_values), 1) if confidence_values else 0,
        "technical_pass_count": technical_pass,
        "technical_review_count": technical_review,
        "technical_fail_count": technical_fail,
        "technical_unknown_count": technical_unknown,
        "evidence_sources": _join(evidence_sources),
        "commercial_position": position,
        "product_intelligence_score": round(max(0, min(100, score)), 1),
        "recommended_action": _product_action(position, technical_fail, technical_unknown),
        "source_layer": "predictive_product",
    }


def build_manufacturer_intelligence_dataset(
    manufacturer_entities: pd.DataFrame,
    product_intelligence: pd.DataFrame,
    manufacturer_history: pd.DataFrame | None = None,
    procurement_matches: pd.DataFrame | None = None,
) -> pd.DataFrame:
    entities = _rows(manufacturer_entities)
    products_by_entity: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in _rows(product_intelligence):
        if _text(row.get("manufacturer_entity_id")):
            products_by_entity[_text(row.get("manufacturer_entity_id"))].append(row)

    history_by_key = {
        manufacturer_key(row.get("manufacturer_name") or row.get("brand_name")): row
        for row in _rows(manufacturer_history)
        if manufacturer_key(row.get("manufacturer_name") or row.get("brand_name"))
    }

    explicit_demand: dict[str, set[str]] = defaultdict(set)
    family_demand: dict[str, set[str]] = defaultdict(set)
    procurement_rows = _rows(procurement_matches)
    for row in procurement_rows:
        event_id = _text(row.get("procurement_event_id"))
        for name in _split(row.get("manufacturer_names")):
            explicit_demand[manufacturer_key(name)].add(event_id)
        family = _normalize(row.get("product_family"))
        if family and event_id and _text(row.get("match_status")) != "UNMATCHED":
            family_demand[family].add(event_id)

    output = []
    for entity in entities:
        entity_id = _text(entity.get("manufacturer_entity_id"))
        name = _text(entity.get("manufacturer_name"))
        products = products_by_entity.get(entity_id, [])
        history = history_by_key.get(manufacturer_key(name), {})
        catalogue_products = [row for row in products if row.get("catalogue_status") == "CONTROLLED_CATALOGUE"]
        historical_products = [row for row in products if _integer(row.get("historical_quote_count")) > 0]
        active_products = [row for row in catalogue_products if _normalize(row.get("principal_status")) in ACTIVE_PRINCIPAL_STATUSES]
        pending_products = [row for row in catalogue_products if _normalize(row.get("principal_status")) in PENDING_PRINCIPAL_STATUSES]
        families = {_normalize(row.get("product_family")) for row in products if _normalize(row.get("product_family"))}
        aligned_events = set().union(*(family_demand[family] for family in families)) if families else set()
        explicit_events = explicit_demand.get(manufacturer_key(name), set())
        quote_count = sum(_integer(row.get("historical_quote_count")) for row in products)
        award_count = _integer(entity.get("procurement_award_count")) or _integer(history.get("award_count"))
        actionable = sum(_integer(row.get("actionable_match_count")) for row in products)
        technical_pass = sum(_integer(row.get("technical_pass_count")) for row in products)
        technical_review = sum(_integer(row.get("technical_review_count")) for row in products)
        technical_fail = sum(_integer(row.get("technical_fail_count")) for row in products)
        technical_unknown = sum(_integer(row.get("technical_unknown_count")) for row in products)

        if active_products:
            coverage_status = "ACTIVE_PRINCIPAL"
        elif catalogue_products:
            coverage_status = "PRINCIPAL_VALIDATION_REQUIRED"
        elif historical_products:
            coverage_status = "HISTORICAL_EVIDENCE_ONLY"
        elif award_count or explicit_events:
            coverage_status = "MARKET_EVIDENCE_ONLY"
        else:
            coverage_status = "REVIEW_REQUIRED"

        score = min(25, len(catalogue_products) * 4)
        score += min(25, len(active_products) * 10)
        score += min(15, quote_count * 4)
        score += min(15, award_count * 5)
        score += min(10, len(explicit_events) * 3)
        score += min(10, len(aligned_events) * 2)
        score += min(5, _integer(entity.get("activity_count")) * 2)
        score += min(10, actionable * 5)
        score -= min(15, technical_fail * 10)
        score = round(max(0, min(100, score)), 1)

        if coverage_status == "PRINCIPAL_VALIDATION_REQUIRED" and score >= 20:
            priority = "Principal validation"
        elif coverage_status == "HISTORICAL_EVIDENCE_ONLY" and quote_count >= 2:
            priority = "Relationship validation"
        elif score >= 75:
            priority = "Strategic manufacturer"
        elif score >= 55:
            priority = "Priority manufacturer"
        elif score >= 35:
            priority = "Development manufacturer"
        else:
            priority = "Monitor"

        if coverage_status == "ACTIVE_PRINCIPAL":
            action = "Review aligned demand, product compliance, pricing, stock, and territory before bid selection."
        elif coverage_status == "PRINCIPAL_VALIDATION_REQUIRED":
            action = "Confirm current principal authorization and territory for the controlled catalogue products."
        elif coverage_status == "HISTORICAL_EVIDENCE_ONLY":
            action = "Validate the current relationship and territory before promoting historical products into the controlled catalogue."
        elif coverage_status == "MARKET_EVIDENCE_ONLY":
            action = "Assess manufacturer fit and route-to-market without assuming Faram representation."
        else:
            action = "Collect stronger manufacturer, product, and commercial evidence."

        evidence = set(_split(entity.get("evidence_sources")))
        evidence.update(source for row in products for source in _split(row.get("evidence_sources")))
        output.append({
            "manufacturer_intelligence_id": _stable_id("manufacturer_intel", entity_id),
            "manufacturer_entity_id": entity_id,
            "manufacturer_name": name,
            "manufacturer_aliases": _text(entity.get("manufacturer_aliases")),
            "coverage_status": coverage_status,
            "commercial_priority": priority,
            "commercial_score": score,
            "catalogue_product_count": len(catalogue_products),
            "active_product_count": len(active_products),
            "pending_product_count": len(pending_products),
            "historical_product_count": len(historical_products),
            "historical_quote_count": quote_count,
            "procurement_award_count": award_count,
            "explicit_demand_count": len(explicit_events),
            "aligned_market_demand_count": len(aligned_events),
            "actionable_match_count": actionable,
            "technical_pass_count": technical_pass,
            "technical_review_count": technical_review,
            "technical_fail_count": technical_fail,
            "technical_unknown_count": technical_unknown,
            "product_families": _join(row.get("product_family") for row in products),
            "equipment_categories": _join(row.get("market_equipment_category") for row in products) or _text(entity.get("equipment_categories")),
            "product_names": _join((row.get("product_name") for row in products), limit=12),
            "models": _join((row.get("model") for row in products), limit=12),
            "principal_statuses": _join(row.get("principal_status") for row in catalogue_products) or _text(entity.get("principal_statuses")),
            "territories": _join(row.get("territory") for row in catalogue_products) or _text(entity.get("territories")),
            "country_codes": _text(entity.get("country_codes")),
            "top_countries": _text(entity.get("top_countries")),
            "buyers": _text(history.get("buyers")),
            "suppliers": _text(history.get("suppliers")),
            "latest_evidence_date": _text(history.get("latest_evidence_date")) or _text(entity.get("latest_evidence_date")),
            "evidence_sources": _join(evidence),
            "recommended_action": action,
            "source_layer": "predictive_product",
        })

    if not output:
        return pd.DataFrame(columns=MANUFACTURER_INTELLIGENCE_COLUMNS)
    return (
        pd.DataFrame(output, columns=MANUFACTURER_INTELLIGENCE_COLUMNS)
        .sort_values(
            by=["commercial_score", "catalogue_product_count", "historical_quote_count", "manufacturer_name"],
            ascending=[False, False, False, True],
        )
        .reset_index(drop=True)
    )


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _update_metadata(data_dir: Path, datasets: dict[str, pd.DataFrame]) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest_path = data_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for name, dataframe in datasets.items():
            manifest.setdefault("row_counts", {})[name] = int(len(dataframe))
            manifest.setdefault("files", {})[name] = f"{name}.csv"
        manifest["product_intelligence_generated_at"] = timestamp
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    summary_path = data_dir / "market_summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary.setdefault("layer_counts", {}).setdefault("canonical", {})[
            "manufacturer_entities"
        ] = int(len(datasets["manufacturer_entities"]))
        predictive = summary.setdefault("layer_counts", {}).setdefault(
            "predictive_product", {}
        )
        predictive["product_intelligence"] = int(len(datasets["product_intelligence"]))
        predictive["manufacturer_intelligence"] = int(
            len(datasets["manufacturer_intelligence"])
        )
        metrics = summary.setdefault("metrics", {})
        metrics["products"] = int(len(datasets["product_intelligence"]))
        metrics["manufacturers"] = int(len(datasets["manufacturer_intelligence"]))
        metrics["active_principals"] = int(
            (
                datasets["manufacturer_intelligence"].get(
                    "coverage_status", pd.Series(dtype=str)
                )
                == "ACTIVE_PRINCIPAL"
            ).sum()
        )
        summary["product_intelligence_generated_at"] = timestamp
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def refresh_outputs(data_dir: Path, database: Path | None = None) -> dict[str, pd.DataFrame]:
    opportunities = _read_csv(data_dir / "opportunities.csv")
    catalogue = _read_csv(data_dir / "faram_product_catalogue.csv")
    historical_quotes = _read_csv(data_dir / "faram_historical_quote_summary.csv")
    manufacturer_history = _read_csv(data_dir / "procurement_manufacturer_history.csv")
    procurement_matches = _read_csv(data_dir / "procurement_product_matches.csv")
    faram_matches = _read_csv(data_dir / "faram_product_matches.csv")
    product_fit = _read_csv(data_dir / "faram_product_fit.csv")

    manufacturer_entities = build_manufacturer_entities_dataset(
        opportunities,
        catalogue=catalogue,
        historical_quotes=historical_quotes,
        manufacturer_history=manufacturer_history,
        procurement_matches=procurement_matches,
    )
    product_intelligence = build_product_intelligence_dataset(
        catalogue,
        historical_quotes,
        procurement_matches,
        faram_matches,
        product_fit,
    )
    manufacturer_intelligence = build_manufacturer_intelligence_dataset(
        manufacturer_entities,
        product_intelligence,
        manufacturer_history=manufacturer_history,
        procurement_matches=procurement_matches,
    )
    datasets = {
        "manufacturer_entities": manufacturer_entities,
        "product_intelligence": product_intelligence,
        "manufacturer_intelligence": manufacturer_intelligence,
    }

    for name, dataframe in datasets.items():
        dataframe.to_csv(data_dir / f"{name}.csv", index=False)

    if database:
        database.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(database)
        try:
            for name, dataframe in datasets.items():
                dataframe.to_sql(name, connection, if_exists="replace", index=False)
            connection.commit()
        finally:
            connection.close()

    _update_metadata(data_dir, datasets)
    return datasets


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh evidence-led product and manufacturer intelligence."
    )
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--database", default="data/iati_intelligence.db")
    args = parser.parse_args()
    datasets = refresh_outputs(Path(args.data_dir), Path(args.database))
    print(
        "Product/manufacturer intelligence refreshed: "
        f"{len(datasets['product_intelligence'])} products, "
        f"{len(datasets['manufacturer_intelligence'])} manufacturers"
    )


if __name__ == "__main__":
    main()
