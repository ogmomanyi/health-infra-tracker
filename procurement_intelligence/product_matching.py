"""Identify products and manufacturers from traceable procurement evidence.

Product identity is deliberately conservative. Exact catalogue models and full
product names are verified identities; controlled device phrases are accepted as
product-family evidence; broad clinical or technical terms are review candidates.
Every accepted or review result retains its source, reference, and excerpt.
"""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import re
from pathlib import Path
from typing import Iterable, Mapping

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
    ("Hematology Analyzer", (
        "hematology analyzers", "hematology analyzer", "hematology analysers", "hematology analyser",
        "haematology analyzers", "haematology analyzer", "haematology analysers", "haematology analyser",
        "cbc analyzer", "cbc analyser", "cell counter", "complete blood count", "5 part diff", "5-part diff",
        "3 part diff", "3-part diff", "hematology", "haematology",
    ), "Laboratory Equipment"),
    ("Clinical Chemistry Analyzer", (
        "clinical chemistry analyzers", "clinical chemistry analyzer", "clinical chemistry analysers", "clinical chemistry analyser",
        "biochemistry analyzers", "biochemistry analyzer", "biochemistry analysers", "biochemistry analyser",
        "chemistry analyzers", "chemistry analyzer", "chemistry analysers", "chemistry analyser", "clinical chemistry",
    ), "Laboratory Equipment"),
    ("Immunoassay Analyzer", (
        "immunoassay analyzers", "immunoassay analyzer", "immunoassay analysers", "immunoassay analyser",
        "chemiluminescence immunoassay system", "immunoassay system", "chemiluminescence immunoassay",
        "immunoassay", "clia", "eclia",
    ), "Laboratory Equipment"),
    ("Molecular / PCR System", (
        "real-time pcr systems", "real time pcr systems", "real-time pcr system", "real time pcr system",
        "pcr systems", "pcr system", "pcr machines", "pcr machine", "molecular diagnostic systems",
        "molecular diagnostic system", "gene xpert", "genexpert", "nucleic acid amplification system",
        "pcr", "molecular diagnostic", "molecular diagnostics", "nucleic acid amplification", "naat",
    ), "Diagnostic Equipment"),
    ("Blood Gas Analyzer", ("blood gas analyzers", "blood gas analyzer", "blood gas analysers", "blood gas analyser", "blood gas"), "Laboratory Equipment"),
    ("Coagulation Analyzer", ("coagulation analyzers", "coagulation analyzer", "coagulation analysers", "coagulation analyser", "coagulometer", "hemostasis analyzer", "haemostasis analyzer"), "Laboratory Equipment"),
    ("Microbiology Analyzer", ("microbiology analyzers", "microbiology analyzer", "microbiology analysers", "microbiology analyser", "automated microbiology system", "blood culture system", "automated microbiology", "microbiology identification"), "Laboratory Equipment"),
    ("Apheresis Machine", ("apheresis machines", "apheresis machine", "apheresis systems", "apheresis system", "apheresis"), "Blood Bank Equipment"),
    ("Centrifuge", ("centrifuge", "centrifuges"), "Laboratory Equipment"),
    ("Microscope", ("microscope", "microscopes", "microscopy"), "Laboratory Equipment"),
    ("Autoclave / Sterilizer", ("autoclave", "autoclaves", "sterilizer", "sterilizers", "steriliser", "sterilisers"), "Sterilization"),
    ("Blood Bank Refrigerator / Freezer", ("blood bank refrigerator", "blood bank freezer", "blood refrigerator", "blood freezer", "plasma freezer"), "Blood Bank Equipment"),
    ("Vaccine Refrigerator / Cold Chain", ("vaccine refrigerator", "vaccine freezer", "cold chain equipment", "cold chain", "cold room", "cold storage"), "Cold Chain"),
    ("Ultrasound System", ("ultrasound systems", "ultrasound system", "ultrasound machines", "ultrasound machine", "ultrasound scanner", "ultrasound", "ultrasonography", "sonography"), "Medical Devices"),
    ("Patient Monitor", ("patient monitors", "patient monitor", "patient monitoring system", "multi parameter monitor", "multiparameter monitor", "patient monitoring"), "Medical Devices"),
    ("Ventilator", ("ventilator", "ventilators", "mechanical ventilator", "mechanical ventilation"), "Medical Devices"),
    ("X-Ray System", ("x-ray systems", "x-ray system", "x ray systems", "x ray system", "x-ray machine", "x ray machine", "digital radiography system", "x-ray", "x ray", "radiography", "digital radiography"), "Medical Devices"),
    ("Slit Lamp", ("slit lamp", "slit-lamp"), "Ophthalmology"),
    ("Tonometer", ("tonometer", "tonometry"), "Ophthalmology"),
    ("Fundus Camera", ("fundus camera", "retinal camera", "fundoscopy"), "Ophthalmology"),
    ("Pipette", ("pipette", "pipettes", "micropipette", "micropipettes"), "Laboratory Equipment"),
]

AMBIGUOUS_PRODUCT_PATTERNS = {
    "hematology", "haematology", "complete blood count", "5 part diff", "5-part diff",
    "3 part diff", "3-part diff", "clinical chemistry", "chemiluminescence immunoassay",
    "immunoassay", "clia", "eclia", "pcr", "molecular diagnostic", "molecular diagnostics",
    "nucleic acid amplification", "naat", "blood gas", "automated microbiology",
    "microbiology identification", "apheresis", "microscopy", "cold chain", "cold room",
    "cold storage", "ultrasound", "ultrasonography", "sonography", "patient monitoring",
    "mechanical ventilation", "x-ray", "x ray", "radiography", "digital radiography",
    "tonometry", "fundoscopy",
}

MANUFACTURER_ALIASES: dict[str, tuple[str, ...]] = {
    "Abbott": ("abbott",), "Beckman Coulter": ("beckman coulter",),
    "Becton Dickinson": ("becton dickinson", "bd biosciences"),
    "Bio-Rad": ("bio-rad", "biorad"), "bioMérieux": ("biomerieux", "biomérieux"),
    "Cepheid": ("cepheid",), "Danaher": ("danaher",), "Fujifilm": ("fujifilm",),
    "GE HealthCare": ("ge healthcare", "ge health care", "general electric healthcare"),
    "Hologic": ("hologic",), "Mindray": ("mindray",), "Nihon Kohden": ("nihon kohden",),
    "Roche": ("roche",), "Siemens Healthineers": ("siemens healthineers", "siemens healthcare"),
    "Sysmex": ("sysmex",), "Thermo Fisher": ("thermo fisher", "thermo scientific"),
    "Philips": ("philips",), "B. Braun": ("b. braun", "b braun", "bbraun"),
    "Bausch + Lomb": ("bausch + lomb", "bausch and lomb", "bausch & lomb"),
}
AMBIGUOUS_MANUFACTURER_ALIASES = {"bd", "traceable"}

SOURCE_PRIORITY = {
    "LINE_ITEM_DESCRIPTION": 6, "NOTICE_TITLE": 5, "STRUCTURED_PRODUCT_FAMILY": 4,
    "NOTICE_TEXT": 3, "DOCUMENT_TEXT": 3, "STRUCTURED_EQUIPMENT_CATEGORY": 2,
}
ACCEPTED_IDENTIFICATION_STATUSES = {
    "VERIFIED_MODEL_IDENTITY", "VERIFIED_PRODUCT_IDENTITY", "EVIDENCE_BACKED_FAMILY",
}


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _normalize(value: object) -> str:
    text = _text(value).lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9+]+", " ", text).strip()


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


def _contains(text: str, phrase: str) -> bool:
    return _contains_normalized(_normalize(text), phrase)


def _excerpt(text: object, evidence: object, max_length: int = 240) -> str:
    source = _text(text)
    phrase = _text(evidence)
    if not source:
        return ""
    position = source.casefold().find(phrase.casefold()) if phrase else -1
    if position < 0:
        return source[:max_length] + ("..." if len(source) > max_length else "")
    margin = max(30, (max_length - len(phrase)) // 2)
    start = max(0, position - margin)
    end = min(len(source), position + len(phrase) + margin)
    excerpt = source[start:end]
    return ("..." if start else "") + excerpt + ("..." if end < len(source) else "")


def _reference(event: Mapping[str, object]) -> str:
    return _text(event.get("source_url") or event.get("tender_reference") or event.get("procurement_event_id"))


def _evidence_segments(event: Mapping[str, object]) -> list[dict[str, str]]:
    reference = _reference(event)
    candidates = [
        ("LINE_ITEM_DESCRIPTION", event.get("line_item_description"), reference),
        ("NOTICE_TITLE", event.get("title"), reference),
        ("STRUCTURED_PRODUCT_FAMILY", event.get("product_family"), reference),
        ("NOTICE_TEXT", event.get("notice_text"), reference),
        ("STRUCTURED_EQUIPMENT_CATEGORY", event.get("equipment_category"), reference),
    ]
    segments: list[dict[str, str]] = []
    seen: set[str] = set()
    for source, value, item_reference in candidates:
        text = _text(value)
        normalized = _normalize(text)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        segments.append({"source": source, "reference": item_reference, "text": text})

    document_segments = event.get("_document_evidence_segments")
    if isinstance(document_segments, list):
        for item in document_segments:
            if not isinstance(item, Mapping):
                continue
            text = _text(item.get("text"))
            normalized = _normalize(text)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            segments.append({"source": "DOCUMENT_TEXT", "reference": _text(item.get("reference")), "text": text})
    else:
        text = _text(event.get("document_text"))
        if text and _normalize(text) not in seen:
            segments.append({
                "source": "DOCUMENT_TEXT",
                "reference": _text(event.get("document_url") or reference),
                "text": text,
            })
    return segments


def _is_ambiguous_pattern(pattern: str) -> bool:
    return _normalize(pattern) in {_normalize(item) for item in AMBIGUOUS_PRODUCT_PATTERNS}


def _family_matches_for_text(text: str) -> list[dict[str, object]]:
    normalized_text = _normalize(text)
    hits: list[dict[str, object]] = []
    for family, patterns, category in PRODUCT_FAMILIES:
        matched = [pattern for pattern in patterns if _contains_normalized(normalized_text, pattern)]
        if not matched:
            continue
        strongest = max(matched, key=lambda pattern: (
            not _is_ambiguous_pattern(pattern), len(_normalize(pattern).split()), len(_normalize(pattern)),
        ))
        hits.append({
            "family": family, "category": category, "evidence": strongest,
            "accepted": not _is_ambiguous_pattern(strongest), "matched_pattern_count": len(matched),
        })
    hits.sort(key=lambda hit: (
        bool(hit["accepted"]), len(_normalize(hit["evidence"]).split()),
        len(_normalize(hit["evidence"])), int(hit["matched_pattern_count"]),
    ), reverse=True)
    return hits


def match_product_families(text: str, *, normalized_text: str | None = None) -> list[tuple[str, str, str]]:
    """Return every explicit product candidate, strongest first.

    This compatibility helper includes ambiguous candidates. ``match_events``
    holds those candidates for review rather than treating them as products.
    """
    del normalized_text
    return [(str(hit["family"]), str(hit["category"]), str(hit["evidence"])) for hit in _family_matches_for_text(text)]


def match_product_family(text: str) -> tuple[str, str, str]:
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
        aliases = tuple(dict.fromkeys([manufacturer, *[
            item.strip() for item in _text(row.get("manufacturer_aliases")).split(";") if item.strip()
        ]]))
        if manufacturer and aliases:
            candidates[manufacturer] = tuple(dict.fromkeys([*candidates.get(manufacturer, ()), *aliases]))
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


def _canonical_lookup(
    equipment_rows: Iterable[dict[str, str]], manufacturer_rows: Iterable[dict[str, str]],
) -> tuple[dict[str, str], dict[str, str]]:
    equipment_ids = {
        _text(row.get("equipment_category")).lower(): _text(row.get("equipment_entity_id"))
        for row in equipment_rows if _text(row.get("equipment_category"))
    }
    manufacturer_ids: dict[str, str] = {}
    for row in manufacturer_rows:
        entity_id = _text(row.get("manufacturer_entity_id"))
        names = [_text(row.get("manufacturer_name")), *[item.strip() for item in _text(row.get("manufacturer_aliases")).split(";")]]
        for name in names:
            if name and entity_id:
                manufacturer_ids[_normalize(name)] = entity_id
    return equipment_ids, manufacturer_ids


def match_catalogue_products(
    text: str, catalogue_rows: Iterable[dict[str, str]], *, normalized_text: str | None = None,
) -> list[dict[str, object]]:
    """Resolve exact unique models or distinctive full catalogue product names."""
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
        if normalized_model and model_counts.get(normalized_model) == 1 and _contains_normalized(normalized_text, model):
            method, evidence, confidence = "CATALOGUE_MODEL_EXACT", model, 98.0
        elif len(_normalize(product_name).split()) >= 3 and _contains_normalized(normalized_text, product_name):
            method, evidence, confidence = "CATALOGUE_PRODUCT_EXACT", product_name, 96.0
        if not method:
            continue
        key = product_id or "|".join((_normalize(product_name), _normalize(row.get("manufacturer_name"))))
        if key in seen:
            continue
        seen.add(key)
        matches.append({
            "faram_product_id": product_id, "product_name": product_name, "model": model,
            "manufacturer_name": _text(row.get("manufacturer_name")),
            "product_family": _text(row.get("product_family")),
            "equipment_category": _text(row.get("equipment_category")),
            "method": method, "evidence": evidence, "confidence": confidence,
        })
    return matches


def _catalogue_matches_for_segments(
    segments: list[dict[str, str]], catalogue_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    selected: dict[str, dict[str, object]] = {}
    for segment in segments:
        for match in match_catalogue_products(segment["text"], catalogue_rows):
            key = _text(match.get("faram_product_id")) or "|".join((
                _normalize(match.get("product_name")), _normalize(match.get("manufacturer_name")),
            ))
            enriched = {
                **match, "evidence_source": segment["source"], "evidence_reference": segment["reference"],
                "evidence_excerpt": _excerpt(segment["text"], match.get("evidence")),
            }
            current = selected.get(key)
            rank = (match.get("method") == "CATALOGUE_MODEL_EXACT", SOURCE_PRIORITY.get(segment["source"], 0))
            current_rank = (
                bool(current and current.get("method") == "CATALOGUE_MODEL_EXACT"),
                SOURCE_PRIORITY.get(str(current.get("evidence_source")), 0) if current else -1,
            )
            if current is None or rank > current_rank:
                selected[key] = enriched
    return list(selected.values())


def _family_candidates_for_segments(segments: list[dict[str, str]]) -> list[dict[str, object]]:
    selected: dict[str, dict[str, object]] = {}
    for segment in segments:
        for hit in _family_matches_for_text(segment["text"]):
            family = str(hit["family"])
            candidate = {
                **hit, "evidence_source": segment["source"], "evidence_reference": segment["reference"],
                "evidence_excerpt": _excerpt(segment["text"], hit["evidence"]), "segment_text": segment["text"],
            }
            current = selected.get(_normalize(family))
            rank = (
                bool(hit["accepted"]), len(_normalize(hit["evidence"]).split()), len(_normalize(hit["evidence"])),
                SOURCE_PRIORITY.get(segment["source"], 0),
            )
            current_rank = (
                bool(current and current["accepted"]),
                len(_normalize(current.get("evidence")).split()) if current else -1,
                len(_normalize(current.get("evidence"))) if current else -1,
                SOURCE_PRIORITY.get(str(current.get("evidence_source")), 0) if current else -1,
            )
            if current is None or rank > current_rank:
                selected[_normalize(family)] = candidate
    return list(selected.values())


def _line_item_id(event_id: str, family: str, evidence: str) -> str:
    key = "|".join((event_id, family, evidence)).casefold()
    return "proc_item_" + sha256(key.encode("utf-8")).hexdigest()[:20]


def _controlled_confidence(candidate: Mapping[str, object]) -> float:
    source = str(candidate.get("evidence_source") or "")
    words = len(_normalize(candidate.get("evidence")).split())
    base = 86.0 if source in {"NOTICE_TITLE", "LINE_ITEM_DESCRIPTION"} else 83.0
    return min(92.0, base + min(4.0, max(0, words - 2) * 2.0))


def match_events(
    events: list[dict[str, object]],
    equipment_rows: list[dict[str, str]] | None = None,
    manufacturer_rows: list[dict[str, str]] | None = None,
    catalogue_rows: list[dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    """Return auditable product-identification records for procurement events."""
    equipment_ids, manufacturer_ids = _canonical_lookup(equipment_rows or [], manufacturer_rows or [])
    results: list[dict[str, object]] = []
    for event in events:
        segments = _evidence_segments(event)
        family_candidates = _family_candidates_for_segments(segments)
        catalogue_matches = _catalogue_matches_for_segments(segments, catalogue_rows or [])
        candidate_by_family = {_normalize(item["family"]): item for item in family_candidates}
        for catalogue_match in catalogue_matches:
            family = _text(catalogue_match.get("product_family"))
            if family and _normalize(family) not in candidate_by_family:
                candidate = {
                    "family": family, "category": _text(catalogue_match.get("equipment_category")),
                    "evidence": _text(catalogue_match.get("evidence")), "accepted": True,
                    "evidence_source": _text(catalogue_match.get("evidence_source")),
                    "evidence_reference": _text(catalogue_match.get("evidence_reference")),
                    "evidence_excerpt": _text(catalogue_match.get("evidence_excerpt")), "segment_text": "",
                }
                family_candidates.append(candidate)
                candidate_by_family[_normalize(family)] = candidate

        all_text = " ".join(segment["text"] for segment in segments)
        event_manufacturer_matches = match_manufacturers(all_text, manufacturer_rows or [])
        if not family_candidates:
            family_candidates = [{
                "family": "", "category": "", "evidence": "", "accepted": False,
                "evidence_source": "", "evidence_reference": "", "evidence_excerpt": "", "segment_text": "",
            }]

        family_count = sum(bool(item.get("family")) for item in family_candidates)
        for candidate in family_candidates:
            candidate_family = _text(candidate.get("family"))
            family_catalogue_matches = [
                match for match in catalogue_matches
                if _normalize(match.get("product_family")) == _normalize(candidate_family)
            ]
            strongest_catalogue = max(
                family_catalogue_matches,
                key=lambda item: (item.get("method") == "CATALOGUE_MODEL_EXACT", float(item.get("confidence") or 0)),
                default=None,
            )
            if strongest_catalogue:
                identification_method = _text(strongest_catalogue.get("method"))
                identification_status = (
                    "VERIFIED_MODEL_IDENTITY" if identification_method == "CATALOGUE_MODEL_EXACT"
                    else "VERIFIED_PRODUCT_IDENTITY"
                )
                accepted_family = candidate_family
                product_evidence = _text(strongest_catalogue.get("evidence"))
                evidence_source = _text(strongest_catalogue.get("evidence_source"))
                evidence_reference = _text(strongest_catalogue.get("evidence_reference"))
                evidence_excerpt = _text(strongest_catalogue.get("evidence_excerpt"))
                confidence = float(strongest_catalogue.get("confidence") or 0)
                review_reason = ""
            elif candidate_family and bool(candidate.get("accepted")):
                identification_method = "CONTROLLED_PHRASE_EXACT"
                identification_status = "EVIDENCE_BACKED_FAMILY"
                accepted_family = candidate_family
                product_evidence = _text(candidate.get("evidence"))
                evidence_source = _text(candidate.get("evidence_source"))
                evidence_reference = _text(candidate.get("evidence_reference"))
                evidence_excerpt = _text(candidate.get("evidence_excerpt"))
                confidence = _controlled_confidence(candidate)
                review_reason = ""
            elif candidate_family:
                identification_method = "AMBIGUOUS_TERM"
                identification_status = "REVIEW_REQUIRED"
                accepted_family = ""
                product_evidence = _text(candidate.get("evidence"))
                evidence_source = _text(candidate.get("evidence_source"))
                evidence_reference = _text(candidate.get("evidence_reference"))
                evidence_excerpt = _text(candidate.get("evidence_excerpt"))
                confidence = 45.0
                review_reason = (
                    f"'{product_evidence}' indicates a clinical or technical context but does not prove a specific "
                    "product. Confirm a device noun, exact model, or full catalogue product name."
                )
            else:
                identification_method = "NONE"
                identification_status = "NO_PRODUCT_IDENTIFIED"
                accepted_family = ""
                product_evidence = evidence_source = evidence_reference = evidence_excerpt = ""
                confidence = 0.0
                review_reason = "No product-specific phrase, exact model, or full catalogue product name was found."

            segment_manufacturers = match_manufacturers(_text(candidate.get("segment_text")), manufacturer_rows or [])
            explicit_manufacturers = (
                [name for name, _ in segment_manufacturers]
                if family_count > 1 else [name for name, _ in event_manufacturer_matches]
            )
            manufacturers = list(dict.fromkeys([
                *explicit_manufacturers,
                *[_text(match.get("manufacturer_name")) for match in family_catalogue_matches if _text(match.get("manufacturer_name"))],
            ]))
            model_evidence = "; ".join(dict.fromkeys(
                _text(match.get("model")) for match in family_catalogue_matches
                if match.get("method") == "CATALOGUE_MODEL_EXACT" and _text(match.get("model"))
            ))
            product_name_evidence = "; ".join(dict.fromkeys(
                _text(match.get("product_name")) for match in family_catalogue_matches
                if match.get("method") == "CATALOGUE_PRODUCT_EXACT" and _text(match.get("product_name"))
            ))
            catalogue_methods = {_text(match.get("method")) for match in family_catalogue_matches}
            manufacturer_method = (
                "CATALOGUE_MODEL_EXACT" if "CATALOGUE_MODEL_EXACT" in catalogue_methods
                else "CATALOGUE_PRODUCT_EXACT" if "CATALOGUE_PRODUCT_EXACT" in catalogue_methods
                else "EXPLICIT_ALIAS" if explicit_manufacturers else ""
            )
            manufacturer_confidence = (
                98.0 if manufacturer_method == "CATALOGUE_MODEL_EXACT"
                else 96.0 if manufacturer_method == "CATALOGUE_PRODUCT_EXACT"
                else 85.0 if manufacturer_method == "EXPLICIT_ALIAS" else 0.0
            )
            if identification_status in ACCEPTED_IDENTIFICATION_STATUSES and manufacturers:
                match_status = "MATCHED_PRODUCT_AND_MANUFACTURER"
            elif identification_status in ACCEPTED_IDENTIFICATION_STATUSES:
                match_status = "MATCHED_PRODUCT_FAMILY"
            elif identification_status == "REVIEW_REQUIRED":
                match_status = "PRODUCT_REVIEW_REQUIRED"
            elif manufacturers:
                match_status = "MANUFACTURER_ONLY"
            else:
                match_status = "UNMATCHED"

            if identification_status == "REVIEW_REQUIRED":
                recommended_action = "Review the cited excerpt and confirm an explicit device, model, or catalogue product before using this product signal."
            elif identification_status.startswith("VERIFIED_") and manufacturers:
                recommended_action = "Validate specification compliance, manufacturer authorization, territory and route-to-market."
            elif accepted_family and manufacturers:
                recommended_action = "Verify manufacturer authorization, specification compliance and route-to-market."
            elif accepted_family:
                recommended_action = "Identify a compliant principal/manufacturer and validate the tender specification."
            elif manufacturers:
                recommended_action = "Assess the named manufacturer's product fit without inferring an unstated product."
            else:
                recommended_action = "Retain as unclassified demand until product-specific evidence is available."

            category = _text(candidate.get("category"))
            event_id = _text(event.get("procurement_event_id"))
            identity_key = accepted_family or candidate_family
            evidence_parts = []
            if product_evidence:
                if identification_method == "CONTROLLED_PHRASE_EXACT":
                    evidence_parts.append(f"product family phrase: {product_evidence}")
                else:
                    evidence_parts.append(f"{identification_method}: {product_evidence}")
            if manufacturers:
                evidence_parts.append(f"manufacturer: {manufacturer_method}")
            results.append({
                "procurement_line_item_id": _line_item_id(event_id, identity_key, product_evidence),
                "procurement_process_id": _text(event.get("procurement_process_id")),
                "procurement_release_id": _text(event.get("procurement_release_id")),
                "procurement_event_id": event_id, "source": _text(event.get("source")),
                "source_url": _text(event.get("source_url")), "tender_reference": _text(event.get("tender_reference")),
                "title": _text(event.get("title")), "buyer": _text(event.get("buyer")),
                "country": _text(event.get("country")), "publication_date": _text(event.get("publication_date")),
                "closing_date": _text(event.get("closing_date")),
                "matched_iati_identifier": _text(event.get("matched_iati_identifier")),
                "line_item_description": _text(event.get("line_item_description")) or evidence_excerpt or _text(event.get("title")),
                "procurement_category": category, "product_family": accepted_family,
                "candidate_product_family": candidate_family if not accepted_family else "",
                "equipment_entity_id": equipment_ids.get(category.lower(), "") if category else "",
                "manufacturer_names": "; ".join(manufacturers),
                "manufacturer_entity_ids": "; ".join(dict.fromkeys(
                    manufacturer_ids.get(_normalize(name), "") for name in manufacturers
                    if manufacturer_ids.get(_normalize(name), "")
                )),
                "manufacturer_match_method": manufacturer_method,
                "manufacturer_match_confidence": manufacturer_confidence,
                "product_identification_status": identification_status,
                "product_identification_method": identification_method,
                "product_identification_confidence": round(confidence, 1),
                "product_evidence": product_evidence, "product_evidence_source": evidence_source,
                "product_evidence_reference": evidence_reference, "product_evidence_excerpt": evidence_excerpt,
                "product_review_reason": review_reason, "model_evidence": model_evidence,
                "product_name_evidence": product_name_evidence,
                "manufacturer_evidence": (
                    "catalogue_identity" if family_catalogue_matches
                    else "explicit_same_evidence_segment" if segment_manufacturers
                    else "explicit_event_text" if explicit_manufacturers else ""
                ),
                "match_confidence": round(confidence, 1), "match_status": match_status,
                "match_evidence": "; ".join(evidence_parts), "recommended_action": recommended_action,
            })
    return results


OUTPUT_FIELDS = [
    "procurement_line_item_id", "procurement_process_id", "procurement_release_id",
    "procurement_event_id", "source", "source_url", "tender_reference", "title", "buyer", "country",
    "publication_date", "closing_date", "matched_iati_identifier", "procurement_category",
    "line_item_description", "product_family", "candidate_product_family", "equipment_entity_id",
    "manufacturer_names", "manufacturer_entity_ids", "manufacturer_match_method",
    "manufacturer_match_confidence", "product_identification_status", "product_identification_method",
    "product_identification_confidence", "product_evidence", "product_evidence_source",
    "product_evidence_reference", "product_evidence_excerpt", "product_review_reason",
    "model_evidence", "product_name_evidence", "manufacturer_evidence", "match_confidence",
    "match_status", "match_evidence", "recommended_action",
]


def write_matches(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Identify procurement products from traceable evidence.")
    parser.add_argument("--events", default="data/procurement_events.csv")
    parser.add_argument("--equipment-entities", default="data/equipment_entities.csv")
    parser.add_argument("--manufacturer-entities", default="data/manufacturer_entities.csv")
    parser.add_argument("--catalogue", default="data/faram_product_catalogue.csv")
    parser.add_argument("--document-evidence", default="data/procurement_document_evidence.csv")
    parser.add_argument("--output", default="data/procurement_product_matches.csv")
    parser.add_argument("--line-items-output", default="data/procurement_line_items.csv")
    args = parser.parse_args()

    events: list[dict[str, object]] = list(_load_rows(Path(args.events)))
    equipment = _load_rows(Path(args.equipment_entities))
    manufacturers = _load_rows(Path(args.manufacturer_entities))
    catalogue = _load_rows(Path(args.catalogue))
    document_evidence = _load_rows(Path(args.document_evidence))
    allowed_documents = {
        _text(event.get("procurement_event_id")): set(decode_document_urls(event.get("document_urls"))) for event in events
    }
    documents_by_event: dict[str, list[dict[str, str]]] = {}
    for row in document_evidence:
        if row.get("extraction_status") != "EXTRACTED":
            continue
        event_id = _text(row.get("procurement_event_id"))
        document_url = _text(row.get("document_url"))
        if not is_valid_document_url(document_url) or document_url not in allowed_documents.get(event_id, set()):
            continue
        documents_by_event.setdefault(event_id, []).append({
            "text": _text(row.get("document_text"))[:50000], "reference": document_url,
        })
    for event in events:
        event["_document_evidence_segments"] = documents_by_event.get(_text(event.get("procurement_event_id")), [])

    rows = match_events(events, equipment, manufacturers, catalogue)
    write_matches(Path(args.output), rows)
    write_matches(Path(args.line_items_output), rows)
    accepted = sum(row["product_identification_status"] in ACCEPTED_IDENTIFICATION_STATUSES for row in rows)
    review = sum(row["product_identification_status"] == "REVIEW_REQUIRED" for row in rows)
    named = sum(bool(row["manufacturer_names"]) for row in rows)
    print(
        f"Product identification completed: {len(events)} events, {len(rows)} evidence records, "
        f"{accepted} accepted identities, {review} review candidates, {named} with manufacturer evidence"
    )


if __name__ == "__main__":
    main()
