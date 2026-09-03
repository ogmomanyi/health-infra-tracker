"""Normalize historical Faram commercial evidence into a richer memory layer.

The source ledger remains authoritative. This module adds normalized event fields
without treating historical evidence as proof of current representation.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable


MEMORY_FIELDS = [
    "memory_id",
    "evidence_id",
    "event_date",
    "supplier_company",
    "supplier_email",
    "manufacturer_name",
    "product_family",
    "product_name",
    "model",
    "category",
    "evidence_type",
    "country",
    "customer_or_project",
    "outcome",
    "evidence_strength",
    "representation_signal",
    "source_email_id",
    "notes",
]

_WEIGHTS = {
    "quotation_and_tender_support": 4,
    "tender_fit_and_pricing": 4,
    "order_and_business_review": 5,
    "quotation": 3,
    "quotation_inquiry": 3,
    "tender_compliance_and_quotation": 4,
    "quotation_and_technical_support": 3,
    "tender_support": 3,
    "tender_bid_support": 3,
    "market_evaluation_and_pricing": 2,
    "partnership_and_tender_support": 2,
    "project_inquiry": 2,
    "procurement_inquiry": 2,
    "request_for_pricing": 2,
    "quotation_and_partnership": 3,
    "quotation_follow_up": 3,
    "tender_or_product_pricing": 3,
}


_EXPLICIT_OUTCOMES = {
    "order_and_business_review": "ORDERED",
    "quotation": "QUOTED",
    "quotation_inquiry": "QUOTED",
    "quotation_and_tender_support": "TENDER_SUPPORT",
    "quotation_and_technical_support": "QUOTED",
    "quotation_and_compliance": "QUOTED",
    "tender_fit_and_pricing": "TENDER_SUPPORT",
    "tender_compliance_and_quotation": "TENDER_SUPPORT",
    "tender_support": "TENDER_SUPPORT",
    "tender_bid_support": "TENDER_SUPPORT",
    "partnership_and_tender_support": "TENDER_SUPPORT",
    "tender_or_product_pricing": "QUOTED",
    "request_for_pricing": "QUOTED",
    "quotation_follow_up": "QUOTED",
    "quotation_and_partnership": "QUOTED",
}


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def normalize(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _text(value).lower().replace("&", " and ")).strip()


def _supplier_company(email: str) -> str:
    domain = _text(email).split("@", 1)[-1].lower() if "@" in email else ""
    known = {
        "3dhistech.com": "3DHISTECH",
        "midmark.com": "Midmark",
        "shinva.com": "SHINVA",
        "tharmac.de": "Tharmac",
        "healthskybio.com": "HealthSky",
        "pixcell.co": "PixCell",
        "eschweiler-kiel.de": "ESCHWEILER",
        "shengfengpack.com": "Shengfeng Pack",
        "mflab.com": "MF Lab",
        "recarecn.cn": "Recare",
        "blu-med.com": "BLU-MED Response Systems",
        "htds.fr": "HTDS",
        "moldev.com": "Molecular Devices",
        "memmert.com": "Memmert",
        "silverlakeresearch.com": "Silver Lake Research",
        "biopanda.co.uk": "BioPanda",
        "thermofisher.com": "Thermo Fisher Scientific",
        "ansell.com": "Ansell",
        "yicaremedical.com": "YiCare Medical",
        "inflammatix.com": "Inflammatix",
        "medtecs.com": "Medtecs",
        "honodmedical.com": "Honod Medical",
    }
    return known.get(domain, domain)


def _outcome(row: dict[str, str]) -> str:
    et = normalize(row.get("evidence_type")).replace(" ", "_")
    return _EXPLICIT_OUTCOMES.get(et, "NO_OUTCOME_RECORDED")


def _signal(row: dict[str, str]) -> str:
    if normalize(row.get("evidence_id")) == "hqe 005":
        return "EXTERNAL_ONLY"
    et = normalize(row.get("evidence_type"))
    if et == "order and business review":
        return "TRANSACTIONAL"
    notes = normalize(row.get("notes"))
    if "competitive reference" in notes or "not faram representation" in notes or "external procurement" in notes:
        return "COMPETITIVE_REFERENCE" if "competitive" in notes else "EXTERNAL_ONLY"
    if any(token in et for token in ("quotation", "tender", "rfq", "request for pricing", "procurement")):
        return "ACTIVE_COMMERCIAL"
    return "MARKET_EXPLORATION"


def _strength(weight: int) -> str:
    if weight >= 5:
        return "HIGH"
    if weight >= 2:
        return "MEDIUM"
    return "LOW"


def load_evidence(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def normalize_evidence(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    result = []
    for index, row in enumerate(rows, start=1):
        evidence_id = _text(row.get("evidence_id"))
        if not evidence_id:
            continue
        weight = _WEIGHTS.get(normalize(row.get("evidence_type")).replace(" ", "_"), 1)
        memory = {
            "memory_id": f"FCM-{index:04d}",
            "evidence_id": evidence_id,
            "event_date": _text(row.get("event_date")),
            "supplier_company": _supplier_company(_text(row.get("supplier_email"))),
            "supplier_email": _text(row.get("supplier_email")),
            "manufacturer_name": _text(row.get("manufacturer_name")),
            "product_family": _text(row.get("product_family")),
            "product_name": _text(row.get("product_name")),
            "model": _text(row.get("model")),
            "category": _text(row.get("category")),
            "evidence_type": _text(row.get("evidence_type")),
            "country": _text(row.get("country")),
            "customer_or_project": _text(row.get("customer_or_project")),
            "outcome": _outcome(row),
            "evidence_strength": _strength(weight),
            "representation_signal": _signal(row),
            "source_email_id": _text(row.get("source_email_id")),
            "notes": _text(row.get("notes")),
        }
        result.append(memory)
    return result


def write_memory(path: Path, rows: Iterable[dict[str, str]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_evidence(rows)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MEMORY_FIELDS)
        writer.writeheader()
        writer.writerows(normalized)
    return len(normalized)


def build_summary(memory_rows: Iterable[dict[str, str]], catalogue_rows: Iterable[dict[str, str]] = ()) -> list[dict[str, str]]:
    groups: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in memory_rows:
        if _text(row.get("representation_signal")) in {"EXTERNAL_ONLY", "COMPETITIVE_REFERENCE"}:
            continue
        groups[(
            _text(row.get("manufacturer_name")),
            _text(row.get("product_family")),
            _text(row.get("product_name")),
            _text(row.get("model")),
        )].append(row)

    active_catalogue = []
    for row in catalogue_rows:
        active = normalize(row.get("principal_status"))
        active_catalogue.append(row if active in {"active", "current", "yes", "true"} else row)

    summary = []
    for (manufacturer, family, product, model), items in groups.items():
        suppliers = {normalize(row.get("supplier_company")) for row in items if normalize(row.get("supplier_company"))}
        dates = []
        for row in items:
            value = _text(row.get("event_date"))
            if value:
                try:
                    dates.append(datetime.fromisoformat(value.replace("Z", "+00:00")))
                except ValueError:
                    pass
        catalogue_match = "NOT_FOUND"
        for cat in active_catalogue:
            if manufacturer and normalize(cat.get("manufacturer_name")) == normalize(manufacturer):
                if family and normalize(cat.get("product_family")) == normalize(family):
                    catalogue_match = "CATALOGUE_MATCH"
                    break
        weights = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        familiarity = min(10, sum(weights.get(_text(row.get("evidence_strength")), 1) for row in items))
        summary.append({
            "manufacturer_name": manufacturer,
            "product_family": family,
            "product_name": product,
            "model": model,
            "supplier_count": str(len(suppliers)),
            "evidence_count": str(len(items)),
            "latest_event_date": max(dates).date().isoformat() if dates else "",
            "strongest_evidence": max(((_text(row.get("evidence_strength")), row.get("evidence_type", "")) for row in items), key=lambda pair: weights.get(pair[0], 0), default=("", ""))[1],
            "commercial_familiarity_score": str(familiarity),
            "current_catalogue_status": catalogue_match,
        })
    return sorted(summary, key=lambda row: (-int(row["commercial_familiarity_score"]), row["manufacturer_name"].lower(), row["product_family"].lower()))


def write_summary(path: Path, memory_rows: Iterable[dict[str, str]], catalogue_rows: Iterable[dict[str, str]] = ()) -> int:
    fields = ["manufacturer_name", "product_family", "product_name", "model", "supplier_count", "evidence_count", "latest_event_date", "strongest_evidence", "commercial_familiarity_score", "current_catalogue_status"]
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = build_summary(memory_rows, catalogue_rows)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Build Faram commercial memory from historical evidence.")
    parser.add_argument("--evidence", default="data/faram_historical_quote_evidence.csv")
    parser.add_argument("--catalogue", default="data/faram_product_catalogue.csv")
    parser.add_argument("--output", default="data/faram_commercial_memory.csv")
    parser.add_argument("--summary", default="data/faram_commercial_memory_summary.csv")
    args = parser.parse_args()
    evidence = load_evidence(Path(args.evidence))
    catalogue = load_evidence(Path(args.catalogue))
    memory_count = write_memory(Path(args.output), evidence)
    memory = load_evidence(Path(args.output))
    summary_count = write_summary(Path(args.summary), memory, catalogue)
    print(f"Faram commercial memory completed: {memory_count} events; {summary_count} grouped records")


if __name__ == "__main__":
    main()
