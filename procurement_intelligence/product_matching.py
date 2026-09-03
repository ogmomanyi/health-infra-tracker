"""Match external procurement notices to product families and known manufacturers.

The matcher is deliberately evidence-based. Product-family matches require explicit
lexical evidence in the notice fields; manufacturer matches require an explicit
manufacturer mention. Existing canonical equipment/manufacturer entities are used
to resolve IDs and reporting context, not to infer an unstated principal.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Iterable


PRODUCT_FAMILIES: list[tuple[str, tuple[str, ...], str]] = [
    ("Hematology Analyzer", ("hematology", "haematology", "complete blood count", "cbc analyzer", "cbc analyser", "cell counter", "5 part diff", "5-part diff", "3 part diff", "3-part diff"), "Laboratory Equipment"),
    ("Clinical Chemistry Analyzer", ("clinical chemistry", "clinical chemistry analyzer", "clinical chemistry analyser", "biochemistry analyzer", "biochemistry analyser", "chemistry analyzer", "chemistry analyser"), "Laboratory Equipment"),
    ("Immunoassay Analyzer", ("immunoassay", "immunoassay analyzer", "immunoassay analyser", "chemiluminescence immunoassay", "clia", "eclia"), "Laboratory Equipment"),
    ("Molecular / PCR System", ("pcr", "molecular diagnostic", "molecular diagnostics", "gene xpert", "genexpert", "nucleic acid amplification", "naat"), "Diagnostic Equipment"),
    ("Blood Gas Analyzer", ("blood gas", "blood gas analyzer", "blood gas analyser"), "Laboratory Equipment"),
    ("Coagulation Analyzer", ("coagulation analyzer", "coagulation analyser", "coagulometer", "hemostasis analyzer", "haemostasis analyzer"), "Laboratory Equipment"),
    ("Microbiology Analyzer", ("microbiology analyzer", "microbiology analyser", "automated microbiology", "microbiology identification", "blood culture system"), "Laboratory Equipment"),
    ("Apheresis Machine", ("apheresis", "apheresis machine", "apheresis system"), "Blood Bank Equipment"),
    ("Centrifuge", ("centrifuge", "centrifuges"), "Laboratory Equipment"),
    ("Microscope", ("microscope", "microscopes", "microscopy"), "Laboratory Equipment"),
    ("Autoclave / Sterilizer", ("autoclave", "autoclaves", "sterilizer", "sterilizers", "steriliser", "sterilisers"), "Sterilization"),
    ("Blood Bank Refrigerator / Freezer", ("blood bank refrigerator", "blood bank freezer", "blood refrigerator", "blood freezer", "plasma freezer"), "Blood Bank Equipment"),
    ("Vaccine Refrigerator / Cold Chain", ("vaccine refrigerator", "vaccine freezer", "cold chain", "cold room", "cold storage"), "Cold Chain"),
    ("Ultrasound System", ("ultrasound", "ultrasonography", "sonography"), "Medical Devices"),
    ("Patient Monitor", ("patient monitor", "patient monitoring", "multi parameter monitor", "multiparameter monitor"), "Medical Devices"),
    ("Ventilator", ("ventilator", "ventilators", "mechanical ventilation"), "Medical Devices"),
    ("X-Ray System", ("x-ray", "x ray", "radiography", "digital radiography"), "Medical Devices"),
    ("Slit Lamp", ("slit lamp", "slit-lamp"), "Ophthalmology"),
    ("Tonometer", ("tonometer", "tonometry"), "Ophthalmology"),
    ("Fundus Camera", ("fundus camera", "fundoscopy", "retinal camera"), "Ophthalmology"),
    ("Pipette", ("pipette", "pipettes", "micropipette", "micropipettes"), "Laboratory Equipment"),
]

MANUFACTURER_ALIASES: dict[str, tuple[str, ...]] = {
    "Abbott": ("abbott",),
    "Beckman Coulter": ("beckman coulter",),
    "Becton Dickinson": ("becton dickinson", "bd biosciences", "bd"),
    "Bio-Rad": ("bio-rad", "biorad"),
    "bioMérieux": ("biomerieux", "biomérieux"),
    "Cepheid": ("cepheid",),
    "Danaher": ("danaher",),
    "Fujifilm": ("fujifilm",),
    "GE HealthCare": ("ge healthcare", "ge health care", "general electric healthcare"),
    "Hologic": ("hologic",),
    "Mindray": ("mindray",),
    "Nihon Kohden": ("nihon kohden",),
    "Roche": ("roche",),
    "Siemens Healthineers": ("siemens healthineers", "siemens healthcare"),
    "Sysmex": ("sysmex",),
    "Thermo Fisher": ("thermo fisher", "thermo scientific"),
    "Philips": ("philips",),
    "B. Braun": ("b. braun", "b braun", "bbraun"),
    "Bausch + Lomb": ("bausch + lomb", "bausch and lomb", "bausch & lomb"),
}


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _normalize(value: object) -> str:
    text = _text(value).lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9+]+", " ", text).strip()


def _contains(text: str, phrase: str) -> bool:
    normalized_text = _normalize(text)
    normalized_phrase = _normalize(phrase)
    if not normalized_phrase:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(normalized_phrase)}(?![a-z0-9])", normalized_text) is not None


def _join_fields(row: dict[str, str]) -> str:
    return " ".join(
        _text(row.get(field))
        for field in ("title", "equipment_category", "product_family", "procurement_stage")
    )


def match_product_family(text: str) -> tuple[str, str, str]:
    """Return (family, category, evidence) for the strongest explicit family match."""
    hits: list[tuple[int, int, str, str, str]] = []
    for family, patterns, category in PRODUCT_FAMILIES:
        matched = [pattern for pattern in patterns if _contains(text, pattern)]
        if matched:
            # Prefer the longest explicit phrase, then the family's catalogue order.
            strongest = max(matched, key=len)
            hits.append((len(strongest)), len(matched), family, category, strongest)

    if not hits:
        return "", "", ""

    hits.sort(key=lambda item: (item[0], item[1]), reverse=True)
    _, _, family, category, evidence = hits[0]
    return family, category, evidence


def match_manufacturers(text: str) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    for manufacturer, aliases in MANUFACTURER_ALIASES.items():
        for alias in aliases:
            if _contains(text, alias):
                matches.append((manufacturer, alias))
                break
    return matches


def _load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _canonical_lookup(equipment_rows: Iterable[dict[str, str]], manufacturer_rows: Iterable[dict[str, str]]) -> tuple[dict[str, str], dict[str, str]]:
    equipment_ids = {
        _text(row.get("equipment_category")).lower(): _text(row.get("equipment_entity_id"))
        for row in equipment_rows
        if _text(row.get("equipment_category"))
    }
    manufacturer_ids = {
        _text(row.get("manufacturer_name")).lower(): _text(row.get("manufacturer_entity_id"))
        for row in manufacturer_rows
        if _text(row.get("manufacturer_name"))
    }
    return equipment_ids, manufacturer_ids


def match_events(
    events: list[dict[str, str]],
    equipment_rows: list[dict[str, str]] | None = None,
    manufacturer_rows: list[dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    """Return one commercial product-match record per procurement event."""
    equipment_ids, manufacturer_ids = _canonical_lookup(equipment_rows or [], manufacturer_rows or [])
    results: list[dict[str, object]] = []

    for event in events:
        text = _join_fields(event)
        family, category, product_evidence = match_product_family(text)
        manufacturers = match_manufacturers(text)
        explicit_manufacturers = [name for name, _ in manufacturers]

        evidence_parts: list[str] = []
        if product_evidence:
            evidence_parts.append(f"product family phrase: {product_evidence}")
        if explicit_manufacturers:
            evidence_parts.append("manufacturer explicitly named")

        confidence = 0.0
        if family:
            confidence = 75.0
            if product_evidence and len(product_evidence.split()) >= 2:
                confidence = 85.0
        if explicit_manufacturers:
            confidence = min(100.0, confidence + 10.0 if family else 55.0)

        if family and explicit_manufacturers:
            match_status = "MATCHED_PRODUCT_AND_MANUFACTURER"
        elif family:
            match_status = "MATCHED_PRODUCT_FAMILY"
        elif explicit_manufacturers:
            match_status = "MANUFACTURER_ONLY"
        else:
            match_status = "UNMATCHED"

        recommended_action = ""
        if family and explicit_manufacturers:
            recommended_action = "Verify manufacturer authorization, tender compliance and Faram route-to-market." 
        elif family:
            recommended_action = "Identify compliant principal/manufacturer and validate tender specifications." 
        elif explicit_manufacturers:
            recommended_action = "Assess the named manufacturer's product fit and potential Faram representation route." 
        else:
            recommended_action = "Retain as unclassified procurement demand; improve notice specification evidence." 

        results.append({
            "procurement_event_id": _text(event.get("procurement_event_id")),
            "source": _text(event.get("source")),
            "tender_reference": _text(event.get("tender_reference")),
            "title": _text(event.get("title")),
            "buyer": _text(event.get("buyer")),
            "country": _text(event.get("country")),
            "publication_date": _text(event.get("publication_date")),
            "closing_date": _text(event.get("closing_date")),
            "matched_iati_identifier": _text(event.get("matched_iati_identifier")),
            "procurement_category": category,
            "product_family": family,
            "equipment_entity_id": equipment_ids.get(category.lower(), "") if category else "",
            "manufacturer_names": "; ".join(explicit_manufacturers),
            "manufacturer_entity_ids": "; ".join(
                manufacturer_ids.get(name.lower(), "")
                for name in explicit_manufacturers
                if manufacturer_ids.get(name.lower(), "")
            ),
            "product_evidence": product_evidence,
            "manufacturer_evidence": "explicit_notice_text" if explicit_manufacturers else "",
            "match_confidence": round(confidence, 1),
            "match_status": match_status,
            "match_evidence": "; ".join(evidence_parts),
            "recommended_action": recommended_action,
        })

    return results


def write_matches(path: Path, rows: list[dict[str, object]]) -> None:
    fields = [
        "procurement_event_id", "source", "tender_reference", "title", "buyer", "country",
        "publication_date", "closing_date", "matched_iati_identifier", "procurement_category",
        "product_family", "equipment_entity_id", "manufacturer_names", "manufacturer_entity_ids",
        "product_evidence", "manufacturer_evidence", "match_confidence", "match_status",
        "match_evidence", "recommended_action",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Match procurement notices to product families and explicit manufacturers.")
    parser.add_argument("--events", default="data/procurement_events.csv")
    parser.add_argument("--equipment-entities", default="data/equipment_entities.csv")
    parser.add_argument("--manufacturer-entities", default="data/manufacturer_entities.csv")
    parser.add_argument("--output", default="data/procurement_product_matches.csv")
    args = parser.parse_args()

    events = _load_rows(Path(args.events))
    equipment = _load_rows(Path(args.equipment_entities))
    manufacturers = _load_rows(Path(args.manufacturer_entities))
    rows = match_events(events, equipment, manufacturers)
    write_matches(Path(args.output), rows)

    matched = sum(row["match_status"] in {"MATCHED_PRODUCT_AND_MANUFACTURER", "MATCHED_PRODUCT_FAMILY"} for row in rows)
    named = sum(bool(row["manufacturer_names"]) for row in rows)
    print(f"Procurement product matching completed: {len(rows)} events, {matched} product-family matches, {named} with explicit manufacturer evidence")


if __name__ == "__main__":
    main()
