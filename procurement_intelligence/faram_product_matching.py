"""Match procurement product demand against Faram's controlled product catalogue.

The catalogue is the source of truth for current Faram products, principals and
territory. This module never infers representation from market knowledge.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Iterable


OUTPUT_FIELDS = [
    "procurement_event_id",
    "source",
    "tender_reference",
    "title",
    "buyer",
    "country",
    "publication_date",
    "closing_date",
    "matched_iati_identifier",
    "product_family",
    "faram_product_id",
    "product_name",
    "manufacturer_name",
    "principal_status",
    "territory_fit",
    "keyword_evidence",
    "exclusion_evidence",
    "match_confidence",
    "match_status",
    "recommended_action",
]

ACTIVE_PRINCIPAL_STATUSES = {"active", "approved", "current"}
WILDCARD_TERRITORIES = {"all", "all countries", "global", "worldwide", "any"}
COUNTRY_ALIASES = {
    "kenya": "KE",
    "ke": "KE",
    "uganda": "UG",
    "ug": "UG",
    "rwanda": "RW",
    "rw": "RW",
    "ethiopia": "ET",
    "et": "ET",
    "somalia": "SO",
    "so": "SO",
    "south sudan": "SS",
    "ss": "SS",
    "democratic republic of the congo": "CD",
    "drc": "CD",
    "congo drc": "CD",
    "cd": "CD",
}


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _normalize(value: object) -> str:
    text = _text(value).lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9+/]+", " ", text).strip()


def _tokens(value: object) -> list[str]:
    return [token for token in re.split(r"[;,|\n]+", _text(value)) if _text(token)]


def _contains(text: str, phrase: str) -> bool:
    normalized_text = _normalize(text)
    normalized_phrase = _normalize(phrase)
    if not normalized_phrase:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(normalized_phrase)}(?![a-z0-9])", normalized_text) is not None


def _canonical_country(value: object) -> str:
    normalized = _normalize(value)
    return COUNTRY_ALIASES.get(normalized, normalized.upper() if len(normalized) == 2 else "")


def _territory_codes(value: object) -> set[str]:
    raw = _tokens(value)
    codes: set[str] = set()
    for item in raw:
        normalized = _normalize(item)
        if normalized in WILDCARD_TERRITORIES:
            return set(WILDCARD_TERRITORIES)
        code = _canonical_country(item)
        if code:
            codes.add(code)
    return codes


def _territory_fit(notice_country: object, territory: object) -> str:
    target = _canonical_country(notice_country)
    allowed = _territory_codes(territory)
    if not target or not allowed:
        return "UNKNOWN"
    if allowed & WILDCARD_TERRITORIES:
        return "YES"
    return "YES" if target in allowed else "NO"


def _row_text(row: dict[str, str]) -> str:
    return " ".join(_text(row.get(field)) for field in (
        "title", "product_family", "procurement_category", "equipment_category", "procurement_stage"
    ))


def _family_alignment(notice: dict[str, str], catalogue: dict[str, str]) -> bool:
    notice_family = _normalize(notice.get("product_family"))
    catalogue_family = _normalize(catalogue.get("product_family"))
    if notice_family and catalogue_family and notice_family == catalogue_family:
        return True

    notice_category = _normalize(notice.get("procurement_category") or notice.get("equipment_category"))
    catalogue_category = _normalize(catalogue.get("equipment_category"))
    return bool(notice_category and catalogue_category and notice_category == catalogue_category)


def _keyword_matches(notice_text: str, keywords: object) -> list[str]:
    return [keyword for keyword in _tokens(keywords) if _contains(notice_text, keyword)]


def _exclusion_matches(notice_text: str, exclusions: object) -> list[str]:
    return [keyword for keyword in _tokens(exclusions) if _contains(notice_text, keyword)]


def _is_active_principal(status: object) -> bool:
    return _normalize(status) in ACTIVE_PRINCIPAL_STATUSES


def _load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def match_events(
    procurement_rows: Iterable[dict[str, str]],
    catalogue_rows: Iterable[dict[str, str]],
) -> list[dict[str, object]]:
    """Return every qualifying Faram catalogue candidate for each procurement notice."""
    catalogue = list(catalogue_rows)
    results: list[dict[str, object]] = []

    for procurement in procurement_rows:
        notice_text = _row_text(procurement)
        for product in catalogue:
            if not _family_alignment(procurement, product):
                continue

            keyword_hits = _keyword_matches(notice_text, product.get("keywords"))
            exclusion_hits = _exclusion_matches(notice_text, product.get("exclusion_keywords"))
            territory_fit = _territory_fit(procurement.get("country"), product.get("territory"))
            active = _is_active_principal(product.get("principal_status"))

            # Exact family/category alignment alone is not enough to call a product fit.
            # A controlled keyword match is required unless the catalogue explicitly
            # defines no keywords for that product. Exclusions always override.
            if product.get("keywords") and not keyword_hits:
                continue
            if exclusion_hits:
                status = "BLOCKED_BY_EXCLUSION"
            elif not active:
                status = "NOT_ACTIONABLE_INACTIVE_PRINCIPAL"
            elif territory_fit == "NO":
                status = "NOT_ACTIONABLE_WRONG_TERRITORY"
            elif territory_fit == "UNKNOWN":
                status = "REQUIRES_TERRITORY_REVIEW"
            else:
                status = "FARAM_MATCH"

            confidence = 60.0
            if _normalize(procurement.get("product_family")) == _normalize(product.get("product_family")):
                confidence += 20.0
            if keyword_hits:
                confidence += min(15.0, 5.0 * len(keyword_hits))
            if active:
                confidence += 5.0
            if exclusion_hits:
                confidence = 0.0
            confidence = round(min(100.0, confidence), 1)

            if status == "FARAM_MATCH":
                action = "Engage principal and assess tender compliance, specification fit and bid strategy."
            elif status == "REQUIRES_TERRITORY_REVIEW":
                action = "Verify Faram territory authorization before treating this as commercially actionable."
            elif status == "NOT_ACTIONABLE_WRONG_TERRITORY":
                action = "Do not treat as a Faram opportunity unless territory authorization changes."
            elif status == "NOT_ACTIONABLE_INACTIVE_PRINCIPAL":
                action = "Do not treat as actionable until principal status is confirmed current."
            else:
                action = "Do not match this product; exclusion evidence overrides positive keyword evidence."

            results.append({
                "procurement_event_id": _text(procurement.get("procurement_event_id")),
                "source": _text(procurement.get("source")),
                "tender_reference": _text(procurement.get("tender_reference")),
                "title": _text(procurement.get("title")),
                "buyer": _text(procurement.get("buyer")),
                "country": _text(procurement.get("country")),
                "publication_date": _text(procurement.get("publication_date")),
                "closing_date": _text(procurement.get("closing_date")),
                "matched_iati_identifier": _text(procurement.get("matched_iati_identifier")),
                "product_family": _text(procurement.get("product_family")),
                "faram_product_id": _text(product.get("faram_product_id")),
                "product_name": _text(product.get("product_name")),
                "manufacturer_name": _text(product.get("manufacturer_name")),
                "principal_status": _text(product.get("principal_status")),
                "territory_fit": territory_fit,
                "keyword_evidence": "; ".join(keyword_hits),
                "exclusion_evidence": "; ".join(exclusion_hits),
                "match_confidence": confidence,
                "match_status": status,
                "recommended_action": action,
            })

    return results


def write_matches(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Match procurement demand against Faram's controlled product catalogue.")
    parser.add_argument("--procurement-matches", default="data/procurement_product_matches.csv")
    parser.add_argument("--catalogue", default="data/faram_product_catalogue.csv")
    parser.add_argument("--output", default="data/faram_product_matches.csv")
    args = parser.parse_args()

    procurement = _load_rows(Path(args.procurement_matches))
    catalogue = _load_rows(Path(args.catalogue))
    rows = match_events(procurement, catalogue)
    write_matches(Path(args.output), rows)

    actionable = sum(row["match_status"] == "FARAM_MATCH" for row in rows)
    print(f"Faram catalogue matching completed: {len(rows)} candidate matches, {actionable} actionable Faram matches")


if __name__ == "__main__":
    main()
