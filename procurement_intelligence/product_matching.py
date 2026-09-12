"""Match external procurement notices to product families and known manufacturers.

The matcher is deliberately evidence-based. Product-family matches require explicit
lexical evidence in the notice fields; manufacturer matches require an explicit
manufacturer mention. Existing canonical equipment/manufacturer entities are used
to resolve IDs and reporting context, not to infer an unstated principal.
"""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import re
from pathlib import Path
from typing import Iterable

from .evidence import decode_document_urls, is_valid_document_url


PRODUCT_FAMILIES: list[tuple[str, tuple[str, ...], str]] = [
    ("Multi-Mode Microplate Reader", ("multi-mode microplate reader", "multimode microplate reader", "microplate reader"), "Laboratory Systems"),
    ("Micro-Volume Spectrophotometer", ("micro-volume spectrophotometer", "micro volume spectrophotometer"), "Laboratory Systems"),
    ("UV-VIS Spectrophotometer", ("uv-vis spectrophotometer", "uv vis spectrophotometer"), "Laboratory Systems"),
    ("Biological Safety Cabinet", ("biological safety cabinet", "class ii safety cabinet", "biosafety cabinet"), "Laboratory Systems"),
    ("Colony Counter", ("automatic colony counter", "colony counter"), "Laboratory Systems"),
    ("Laboratory Incubator", ("laboratory incubator", "lab incubator", "incubator oven"), "Laboratory Systems"),
    ("Universal Oven", ("laboratory oven", "universal oven"), "Laboratory Systems"),
    ("Top Loading Balance", ("top loading balance", "precision laboratory balance"), "Laboratory Systems"),
    ("pH Meter", ("ph meter", "ph/ise meter", "ph orp meter"), "Laboratory Systems"),
    ("Membrane Filtration System", ("membrane filtration system", "vacuum filtration system"), "Laboratory Systems"),
    ("Hotplate Stirrer", ("hotplate stirrer", "magnetic stirrer with hotplate"), "Laboratory Systems"),
    ("Vortex Mixer", ("vortex mixer",), "Laboratory Systems"),
    ("Thermoreactor", ("thermoreactor", "cod reactor", "digestion reactor"), "Laboratory Systems"),
    ("Digital Probe Thermometer", ("digital probe thermometer",), "Laboratory Systems"),
    ("Sickle Cell Diagnostic Test", ("sickle cell diagnostic", "sickle cell test kit", "hemotype sc"), "Diagnostic Equipment"),
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
    "Becton Dickinson": ("becton dickinson", "bd biosciences"),
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
AMBIGUOUS_MANUFACTURER_ALIASES = {"bd", "traceable"}


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _normalize(value: object) -> str:
    text = _text(value).lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9+]+", " ", text).strip()


def _contains(text: str, phrase: str) -> bool:
    return _contains_normalized(_normalize(text), phrase)


def _contains_normalized(normalized_text: str, phrase: str) -> bool:
    normalized_phrase = _normalize(phrase)
    if not normalized_phrase:
        return False
    start = normalized_text.find(normalized_phrase)
    while start >= 0:
        end = start + len(normalized_phrase)
        before = normalized_text[start - 1] if start else " "
        after = normalized_text[end] if end < len(normalized_text) else " "
        if not before.isalnum() and not after.isalnum():
            return True
        start = normalized_text.find(normalized_phrase, start + 1)
    return False


def _join_fields(row: dict[str, str]) -> str:
    return " ".join(
        _text(row.get(field))
        for field in (
            "title", "equipment_category", "product_family", "procurement_stage",
            "notice_text", "document_text", "line_item_description",
        )
    )


def match_product_families(
    text: str,
    *,
    normalized_text: str | None = None,
) -> list[tuple[str, str, str]]:
    """Return every explicitly evidenced product family, strongest first."""
    normalized_text = normalized_text if normalized_text is not None else _normalize(text)
    hits: list[tuple[int, int, str, str, str]] = []
    for family, patterns, category in PRODUCT_FAMILIES:
        matched = [
            pattern for pattern in patterns
            if _contains_normalized(normalized_text, pattern)
        ]
        if matched:
            strongest = max(matched, key=len)
            hits.append((len(strongest), len(matched), family, category, strongest))

    hits.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [(family, category, evidence) for _, _, family, category, evidence in hits]


def match_product_family(text: str) -> tuple[str, str, str]:
    """Return the strongest explicit family match for backwards compatibility."""
    hits = match_product_families(text)
    return hits[0] if hits else ("", "", "")


def match_manufacturers(
    text: str,
    manufacturer_rows: Iterable[dict[str, str]] | None = None,
    *,
    normalized_text: str | None = None,
) -> list[tuple[str, str]]:
    normalized_text = normalized_text if normalized_text is not None else _normalize(text)
    candidates = dict(MANUFACTURER_ALIASES)

    for row in manufacturer_rows or []:
        manufacturer = _text(row.get("manufacturer_name"))
        aliases = tuple(
            dict.fromkeys([
                manufacturer,
                *[item.strip() for item in _text(row.get("manufacturer_aliases")).split(";") if item.strip()],
            ])
        )
        if manufacturer and aliases:
            candidates[manufacturer] = tuple(dict.fromkeys([
                *candidates.get(manufacturer, ()),
                *aliases,
            ]))

    matches: list[tuple[str, str]] = []
    seen: set[str] = set()
    for manufacturer, aliases in candidates.items():
        for alias in aliases:
            if _normalize(alias) in AMBIGUOUS_MANUFACTURER_ALIASES:
                continue
            if _contains_normalized(normalized_text, alias):
                key = _normalize(manufacturer)
                if key not in seen:
                    matches.append((manufacturer, alias))
                    seen.add(key)
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
    manufacturer_ids: dict[str, str] = {}
    for row in manufacturer_rows:
        entity_id = _text(row.get("manufacturer_entity_id"))
        names = [
            _text(row.get("manufacturer_name")),
            *[item.strip() for item in _text(row.get("manufacturer_aliases")).split(";")],
        ]
        for name in names:
            if name and entity_id:
                manufacturer_ids[_normalize(name)] = entity_id
    return equipment_ids, manufacturer_ids


def match_catalogue_products(
    text: str,
    catalogue_rows: Iterable[dict[str, str]],
    *,
    normalized_text: str | None = None,
) -> list[dict[str, object]]:
    """Resolve exact, distinctive model or full product-name evidence.

    Catalogue membership proves product identity, not representation status. The
    latter remains governed by the catalogue's principal-status checks downstream.
    """
    rows = list(catalogue_rows)
    normalized_text = normalized_text if normalized_text is not None else _normalize(text)
    model_counts: dict[str, int] = {}
    for row in rows:
        model = _normalize(row.get("model"))
        if len(model.replace(" ", "")) >= 3:
            model_counts[model] = model_counts.get(model, 0) + 1

    matches: list[dict[str, object]] = []
    seen: set[str] = set()
    for row in rows:
        product_id = _text(row.get("faram_product_id"))
        model = _text(row.get("model"))
        product_name = _text(row.get("product_name"))
        method = evidence = ""
        confidence = 0.0
        normalized_model = _normalize(model)
        if (
            normalized_model
            and model_counts.get(normalized_model) == 1
            and _contains_normalized(normalized_text, model)
        ):
            method, evidence, confidence = "MODEL_REGISTRY", model, 95.0
        elif (
            len(_normalize(product_name).split()) >= 3
            and _contains_normalized(normalized_text, product_name)
        ):
            method, evidence, confidence = "PRODUCT_REGISTRY", product_name, 92.0
        if not method:
            continue
        key = product_id or "|".join(
            (_normalize(product_name), _normalize(row.get("manufacturer_name")))
        )
        if key in seen:
            continue
        seen.add(key)
        matches.append({
            "faram_product_id": product_id,
            "product_name": product_name,
            "model": model,
            "manufacturer_name": _text(row.get("manufacturer_name")),
            "product_family": _text(row.get("product_family")),
            "equipment_category": _text(row.get("equipment_category")),
            "method": method,
            "evidence": evidence,
            "confidence": confidence,
        })
    return matches


def _line_item_id(event_id: str, family: str, evidence: str) -> str:
    key = "|".join((event_id, family, evidence)).casefold()
    return "proc_item_" + sha256(key.encode("utf-8")).hexdigest()[:20]


def match_events(
    events: list[dict[str, str]],
    equipment_rows: list[dict[str, str]] | None = None,
    manufacturer_rows: list[dict[str, str]] | None = None,
    catalogue_rows: list[dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    """Return evidence-backed line-item matches for every procurement event."""
    equipment_ids, manufacturer_ids = _canonical_lookup(equipment_rows or [], manufacturer_rows or [])
    results: list[dict[str, object]] = []

    for event in events:
        text = _join_fields(event)
        normalized_text = _normalize(text)
        family_matches = match_product_families(text, normalized_text=normalized_text)
        catalogue_matches = match_catalogue_products(
            text, catalogue_rows or [], normalized_text=normalized_text
        )
        known_families = {_normalize(family) for family, _, _ in family_matches}
        for catalogue_match in catalogue_matches:
            family = _text(catalogue_match.get("product_family"))
            if family and _normalize(family) not in known_families:
                if len(family_matches) == 1 and len(catalogue_matches) == 1:
                    _, lexical_category, lexical_evidence = family_matches[0]
                    family_matches[0] = (
                        family,
                        lexical_category or _text(catalogue_match.get("equipment_category")),
                        lexical_evidence,
                    )
                else:
                    family_matches.append((
                        family,
                        _text(catalogue_match.get("equipment_category")),
                        _text(catalogue_match.get("evidence")),
                    ))
                known_families.add(_normalize(family))

        explicit_matches = match_manufacturers(
            text, manufacturer_rows or [], normalized_text=normalized_text
        )
        explicit_manufacturers = [name for name, _ in explicit_matches]
        if not family_matches:
            family_matches = [("", "", "")]

        for family, category, product_evidence in family_matches:
            family_catalogue_matches = [
                match for match in catalogue_matches
                if _normalize(match.get("product_family")) == _normalize(family)
            ]
            manufacturers = list(dict.fromkeys([
                *explicit_manufacturers,
                *[
                    _text(match.get("manufacturer_name"))
                    for match in family_catalogue_matches
                    if _text(match.get("manufacturer_name"))
                ],
            ]))
            model_evidence = "; ".join(dict.fromkeys(
                _text(match.get("model")) for match in family_catalogue_matches
                if match.get("method") == "MODEL_REGISTRY" and _text(match.get("model"))
            ))
            product_name_evidence = "; ".join(dict.fromkeys(
                _text(match.get("product_name")) for match in family_catalogue_matches
                if match.get("method") == "PRODUCT_REGISTRY" and _text(match.get("product_name"))
            ))
            registry_methods = [str(match.get("method")) for match in family_catalogue_matches]
            manufacturer_method = (
                "MODEL_REGISTRY" if "MODEL_REGISTRY" in registry_methods
                else "PRODUCT_REGISTRY" if "PRODUCT_REGISTRY" in registry_methods
                else "EXPLICIT_ALIAS" if explicit_manufacturers
                else ""
            )
            manufacturer_confidence = (
                95.0 if manufacturer_method == "MODEL_REGISTRY"
                else 92.0 if manufacturer_method == "PRODUCT_REGISTRY"
                else 85.0 if manufacturer_method == "EXPLICIT_ALIAS"
                else 0.0
            )

            evidence_parts: list[str] = []
            if product_evidence:
                evidence_parts.append(f"product family phrase: {product_evidence}")
            if explicit_manufacturers:
                evidence_parts.append("manufacturer explicitly named")
            if model_evidence:
                evidence_parts.append(f"catalogue model: {model_evidence}")
            if product_name_evidence:
                evidence_parts.append(f"catalogue product: {product_name_evidence}")

            confidence = 0.0
            if family:
                confidence = 75.0
                if product_evidence and len(product_evidence.split()) >= 2:
                    confidence = 85.0
            if family_catalogue_matches:
                confidence = max(
                    confidence,
                    max(float(match.get("confidence") or 0) for match in family_catalogue_matches),
                )
            if manufacturers:
                confidence = min(100.0, confidence + 10.0 if family else 55.0)

            if family and manufacturers:
                match_status = "MATCHED_PRODUCT_AND_MANUFACTURER"
            elif family:
                match_status = "MATCHED_PRODUCT_FAMILY"
            elif manufacturers:
                match_status = "MANUFACTURER_ONLY"
            else:
                match_status = "UNMATCHED"

            if family and manufacturers:
                recommended_action = "Verify manufacturer authorization, tender compliance and Faram route-to-market."
            elif family:
                recommended_action = "Identify compliant principal/manufacturer and validate tender specifications."
            elif manufacturers:
                recommended_action = "Assess the named manufacturer's product fit and potential Faram representation route."
            else:
                recommended_action = "Retain as unclassified procurement demand; improve notice specification evidence."

            event_id = _text(event.get("procurement_event_id"))
            results.append({
                "procurement_line_item_id": _line_item_id(event_id, family, product_evidence),
                "procurement_process_id": _text(event.get("procurement_process_id")),
                "procurement_release_id": _text(event.get("procurement_release_id")),
                "procurement_event_id": event_id,
                "source": _text(event.get("source")),
                "tender_reference": _text(event.get("tender_reference")),
                "title": _text(event.get("title")),
                "buyer": _text(event.get("buyer")),
                "country": _text(event.get("country")),
                "publication_date": _text(event.get("publication_date")),
                "closing_date": _text(event.get("closing_date")),
                "matched_iati_identifier": _text(event.get("matched_iati_identifier")),
                "line_item_description": product_evidence or _text(event.get("title")),
                "procurement_category": category,
                "product_family": family,
                "equipment_entity_id": equipment_ids.get(category.lower(), "") if category else "",
                "manufacturer_names": "; ".join(manufacturers),
                "manufacturer_entity_ids": "; ".join(dict.fromkeys(
                    manufacturer_ids.get(_normalize(name), "")
                    for name in manufacturers
                    if manufacturer_ids.get(_normalize(name), "")
                )),
                "manufacturer_match_method": manufacturer_method,
                "manufacturer_match_confidence": manufacturer_confidence,
                "product_evidence": product_evidence,
                "model_evidence": model_evidence,
                "product_name_evidence": product_name_evidence,
                "manufacturer_evidence": (
                    "catalogue_model_or_product" if family_catalogue_matches
                    else "explicit_notice_text" if explicit_manufacturers
                    else ""
                ),
                "match_confidence": round(confidence, 1),
                "match_status": match_status,
                "match_evidence": "; ".join(evidence_parts),
                "recommended_action": recommended_action,
            })

    return results


def write_matches(path: Path, rows: list[dict[str, object]]) -> None:
    fields = [
        "procurement_line_item_id", "procurement_process_id", "procurement_release_id",
        "procurement_event_id", "source", "tender_reference", "title", "buyer", "country",
        "publication_date", "closing_date", "matched_iati_identifier", "procurement_category",
        "line_item_description",
        "product_family", "equipment_entity_id", "manufacturer_names", "manufacturer_entity_ids",
        "manufacturer_match_method", "manufacturer_match_confidence", "product_evidence",
        "model_evidence", "product_name_evidence", "manufacturer_evidence",
        "match_confidence", "match_status",
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
    parser.add_argument("--catalogue", default="data/faram_product_catalogue.csv")
    parser.add_argument("--document-evidence", default="data/procurement_document_evidence.csv")
    parser.add_argument("--output", default="data/procurement_product_matches.csv")
    parser.add_argument("--line-items-output", default="data/procurement_line_items.csv")
    args = parser.parse_args()

    events = _load_rows(Path(args.events))
    equipment = _load_rows(Path(args.equipment_entities))
    manufacturers = _load_rows(Path(args.manufacturer_entities))
    catalogue = _load_rows(Path(args.catalogue))
    document_evidence = _load_rows(Path(args.document_evidence))
    allowed_documents = {
        _text(event.get("procurement_event_id")): set(
            decode_document_urls(event.get("document_urls"))
        )
        for event in events
    }
    document_text: dict[str, list[str]] = {}
    for row in document_evidence:
        if row.get("extraction_status") != "EXTRACTED":
            continue
        event_id = _text(row.get("procurement_event_id"))
        document_url = _text(row.get("document_url"))
        if (
            not is_valid_document_url(document_url)
            or document_url not in allowed_documents.get(event_id, set())
        ):
            continue
        document_text.setdefault(event_id, []).append(
            _text(row.get("document_text"))
        )
    for event in events:
        event["document_text"] = " ".join(
            document_text.get(_text(event.get("procurement_event_id")), [])
        )[:50000]
    rows = match_events(events, equipment, manufacturers, catalogue)
    write_matches(Path(args.output), rows)
    write_matches(Path(args.line_items_output), rows)

    matched = sum(row["match_status"] in {"MATCHED_PRODUCT_AND_MANUFACTURER", "MATCHED_PRODUCT_FAMILY"} for row in rows)
    named = sum(bool(row["manufacturer_names"]) for row in rows)
    print(f"Procurement product matching completed: {len(events)} events, {len(rows)} line items, {matched} product-family matches, {named} with manufacturer evidence")


if __name__ == "__main__":
    main()
