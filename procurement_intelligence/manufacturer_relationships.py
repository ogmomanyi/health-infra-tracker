"""Evidence-led manufacturer affinity for buyers, donors, and receiving parties."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from hashlib import sha256
from pathlib import Path
import re
from typing import Iterable

from organisation_resolution.normalizer import normalize_name


FIELDS = [
    "manufacturer_relationship_id", "party_role", "party_name",
    "organisation_entity_id", "target_account_id", "country",
    "manufacturer_name", "manufacturer_entity_id", "product_families",
    "models", "procurement_event_count", "observed_award_count",
    "specified_notice_count", "explicit_preference_count",
    "model_specification_count", "first_evidence_date", "latest_evidence_date",
    "tender_references", "procurement_event_ids", "iati_project_ids",
    "source_urls", "relationship_signal", "preference_status",
    "relationship_confidence", "recommended_action", "source_layer",
]


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _split(value: object) -> list[str]:
    return [item.strip() for item in re.split(r"[;|\n]+", _text(value)) if item.strip()]


def _join(values: Iterable[object]) -> str:
    return "; ".join(sorted({_text(value) for value in values if _text(value)}))


def _read(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _relationship_id(role: str, party_key: str, manufacturer_key: str, country: str) -> str:
    digest = sha256(
        "|".join((role, party_key, manufacturer_key, country)).encode("utf-8")
    ).hexdigest()[:20]
    return f"mfr_rel_{digest}"


def _manufacturer_index(rows: Iterable[dict[str, str]]) -> dict[str, tuple[str, str]]:
    index: dict[str, tuple[str, str]] = {}
    for row in rows:
        entity_id = _text(row.get("manufacturer_entity_id"))
        canonical = _text(row.get("manufacturer_name"))
        for name in [canonical, *_split(row.get("manufacturer_aliases"))]:
            if name:
                index[normalize_name(name)] = (entity_id, canonical or name)
    return index


def _account_indexes(rows: Iterable[dict[str, str]]) -> tuple[dict[str, str], dict[str, str]]:
    by_entity: dict[str, str] = {}
    by_name: dict[str, str] = {}
    for row in rows:
        account_id = _text(row.get("target_account_id"))
        entity_id = _text(row.get("organisation_entity_id"))
        name = normalize_name(row.get("account_name") or "")
        if account_id and entity_id:
            by_entity[entity_id] = account_id
        if account_id and name:
            by_name[name] = account_id
    return by_entity, by_name


def _buyer_index(rows: Iterable[dict[str, str]]) -> dict[tuple[str, str], tuple[str, str]]:
    index: dict[tuple[str, str], tuple[str, str]] = {}
    for row in rows:
        country = normalize_name(row.get("country") or "")
        entity_id = _text(row.get("entity_id"))
        canonical = _text(row.get("canonical_buyer") or row.get("buyer"))
        for name in [canonical, *_split(row.get("raw_buyer_names"))]:
            if name:
                index[(normalize_name(name), country)] = (entity_id, canonical or name)
    return index


def _resolution_index(rows: Iterable[dict[str, str]]) -> dict[tuple[str, str, str], str]:
    output: dict[tuple[str, str, str], str] = {}
    for row in rows:
        entity_id = _text(row.get("entity_id"))
        if not entity_id:
            continue
        output[(
            _text(row.get("opportunity_id")),
            normalize_name(row.get("organisation_name") or ""),
            _text(row.get("organisation_role")).upper(),
        )] = entity_id
    return output


def _resolved_party(
    project_id: str,
    name: str,
    roles: tuple[str, ...],
    resolutions: dict[tuple[str, str, str], str],
) -> str:
    normalized = normalize_name(name)
    return next(
        (resolutions.get((project_id, normalized, role), "") for role in roles if resolutions.get((project_id, normalized, role))),
        "",
    )


def _contains_term(text: str, term: str) -> bool:
    haystack = re.sub(r"[^a-z0-9]+", " ", _text(text).casefold()).strip()
    needle = re.sub(r"[^a-z0-9]+", " ", _text(term).casefold()).strip()
    return bool(needle) and f" {needle} " in f" {haystack} "


def _explicit_preference(text: str, manufacturer: str, models: Iterable[str] = ()) -> bool:
    preference_pattern = re.compile(
        r"\b(?:preferred|preference)\s+(?:brand|make|manufacturer|model)\b|"
        r"\b(?:brand|make|manufacturer|model)\s+preference\b",
        re.I,
    )
    terms = [manufacturer, *models]
    for match in preference_pattern.finditer(text):
        context = text[max(0, match.start() - 240):match.end() + 240]
        if any(_contains_term(context, term) for term in terms):
            return True
    return False


def _parties_for_event(
    event: dict[str, str],
    project: dict[str, str] | None,
    buyer_index: dict[tuple[str, str], tuple[str, str]],
    resolutions: dict[tuple[str, str, str], str],
    world_bank_projects: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    parties: list[dict[str, str]] = []
    buyer = _text(event.get("buyer"))
    country = _text(event.get("country"))
    buyer_entity, canonical_buyer = buyer_index.get(
        (normalize_name(buyer), normalize_name(country)),
        ("", buyer),
    )
    if buyer:
        parties.append({
            "party_role": "BUYER", "party_name": canonical_buyer or buyer,
            "organisation_entity_id": buyer_entity, "country": country,
        })

    if _text(event.get("source")) == "World Bank":
        metadata = world_bank_projects.get(_text(event.get("project_reference")), {})
        if metadata and _text(metadata.get("fetch_status")) == "SUCCESS":
            parties.append({
                "party_role": "DONOR", "party_name": "World Bank",
                "organisation_entity_id": "", "country": country,
            })
            receiving = [
                *_split(metadata.get("borrower")),
                *_split(metadata.get("implementing_agency")),
            ]
            for name in receiving:
                parties.append({
                    "party_role": "RECEIVING_PARTY", "party_name": name,
                    "organisation_entity_id": "", "country": country,
                })

    if event.get("match_status") != "CONFIRMED" or not project:
        return parties
    project_id = _text(event.get("matched_iati_identifier"))
    for name in _split(project.get("funding_agencies")):
        parties.append({
            "party_role": "DONOR", "party_name": name,
            "organisation_entity_id": _resolved_party(
                project_id, name, ("FUNDING", "REPORTING"), resolutions
            ),
            "country": country,
        })
    receiving = [
        *_split(project.get("implementing_partners")),
        *_split(project.get("accountable_orgs")),
    ]
    for name in receiving:
        parties.append({
            "party_role": "RECEIVING_PARTY", "party_name": name,
            "organisation_entity_id": _resolved_party(
                project_id, name, ("IMPLEMENTING", "ACCOUNTABLE"), resolutions
            ),
            "country": country,
        })
    unique: dict[tuple[str, str, str], dict[str, str]] = {}
    for party in parties:
        key = (
            party["party_role"],
            party["organisation_entity_id"] or normalize_name(party["party_name"]),
            normalize_name(party["country"]),
        )
        unique[key] = party
    return list(unique.values())


def build_manufacturer_relationships(
    product_matches: list[dict[str, str]],
    events: list[dict[str, str]],
    opportunities: list[dict[str, str]],
    buyer_history: list[dict[str, str]],
    organisation_resolutions: list[dict[str, str]],
    target_accounts: list[dict[str, str]],
    manufacturer_entities: list[dict[str, str]],
    world_bank_project_metadata: list[dict[str, str]] | None = None,
    document_evidence: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    events_by_id = {_text(row.get("procurement_event_id")): row for row in events}
    projects = {_text(row.get("iati_identifier")): row for row in opportunities}
    buyers = _buyer_index(buyer_history)
    resolutions = _resolution_index(organisation_resolutions)
    manufacturers = _manufacturer_index(manufacturer_entities)
    accounts_by_entity, accounts_by_name = _account_indexes(target_accounts)
    world_bank_projects = {
        _text(row.get("project_reference")): row
        for row in world_bank_project_metadata or []
        if _text(row.get("project_reference"))
    }
    document_text: dict[str, list[str]] = defaultdict(list)
    for row in document_evidence or []:
        if _text(row.get("extraction_status")) == "EXTRACTED":
            document_text[_text(row.get("procurement_event_id"))].append(
                _text(row.get("document_text"))
            )
    groups: dict[tuple[str, str, str, str], dict[str, object]] = {}
    seen: set[tuple[str, str, str, str, str]] = set()

    for match in product_matches:
        event_id = _text(match.get("procurement_event_id"))
        event = events_by_id.get(event_id)
        if not event:
            continue
        has_product_context = any(_text(match.get(field)) for field in (
            "product_family", "model_evidence", "product_name_evidence",
        ))
        try:
            relevance_score = float(event.get("faram_relevance_score") or 0)
        except (TypeError, ValueError):
            relevance_score = 0.0
        if not has_product_context and relevance_score < 40:
            continue
        manufacturer_names = _split(match.get("manufacturer_names"))
        if not manufacturer_names:
            continue
        project = projects.get(_text(event.get("matched_iati_identifier")))
        evidence_text = " ".join((
            _text(event.get("title")),
            _text(event.get("notice_text")),
            *document_text.get(event_id, []),
        ))
        parties = _parties_for_event(
            event, project, buyers, resolutions, world_bank_projects
        )
        for raw_manufacturer in manufacturer_names:
            entity_id, manufacturer = manufacturers.get(
                normalize_name(raw_manufacturer),
                ("", raw_manufacturer),
            )
            manufacturer_key = entity_id or normalize_name(manufacturer)
            for party in parties:
                party_key = party["organisation_entity_id"] or normalize_name(party["party_name"])
                evidence_key = (
                    event_id, party["party_role"], party_key, manufacturer_key,
                    normalize_name(match.get("product_family") or ""),
                )
                if evidence_key in seen:
                    continue
                seen.add(evidence_key)
                key = (party["party_role"], party_key, manufacturer_key, normalize_name(party["country"]))
                group = groups.setdefault(key, {
                    **party,
                    "manufacturer_name": manufacturer,
                    "manufacturer_entity_id": entity_id,
                    "families": set(), "models": set(), "events": set(),
                    "awards": set(), "notices": set(), "preferences": set(),
                    "model_events": set(), "dates": set(), "references": set(),
                    "projects": set(), "urls": set(),
                })
                group["families"].add(_text(match.get("product_family")))
                group["models"].update(_split(match.get("model_evidence")))
                group["events"].add(event_id)
                if _text(event.get("opportunity_status")) == "AWARD_HISTORY":
                    group["awards"].add(event_id)
                else:
                    group["notices"].add(event_id)
                if _explicit_preference(
                    evidence_text, manufacturer, _split(match.get("model_evidence"))
                ):
                    group["preferences"].add(event_id)
                if _text(match.get("model_evidence")):
                    group["model_events"].add(event_id)
                group["dates"].add(_text(event.get("publication_date")))
                group["references"].add(_text(event.get("tender_reference")))
                group["projects"].add(_text(event.get("matched_iati_identifier")))
                group["urls"].add(_text(event.get("source_url")))

    output: list[dict[str, str]] = []
    for key, group in groups.items():
        awards = len(group["awards"]); notices = len(group["notices"])
        preferences = len(group["preferences"]); models = len(group["model_events"])
        event_count = len(group["events"])
        if preferences:
            signal = "EXPLICIT_PREFERENCE"
            preference_status = "EXPLICIT_SOURCE_PREFERENCE"
            confidence = 95.0
            action = "Validate whether the stated preference remains current and whether alternatives are permitted."
        elif awards:
            signal = "OBSERVED_AWARD_AFFINITY"
            preference_status = "NOT_ESTABLISHED"
            confidence = 90.0 if awards >= 2 else 85.0
            action = "Use award history as incumbent context; verify the next tender remains open to alternatives."
        elif notices >= 2:
            signal = "REPEATED_SPECIFICATION_AFFINITY"
            preference_status = "NOT_ESTABLISHED"
            confidence = 75.0
            action = "Review repeated specifications and engage before the next procurement cycle."
        else:
            signal = "SINGLE_NOTICE_SIGNAL"
            preference_status = "NOT_ESTABLISHED"
            confidence = 65.0 if models else 55.0
            action = "Treat as a single evidence point and seek corroborating procurement history."
        entity_id = _text(group["organisation_entity_id"])
        party_name = _text(group["party_name"])
        target_account_id = accounts_by_entity.get(entity_id, "") or accounts_by_name.get(
            normalize_name(party_name), ""
        )
        dates = sorted(value for value in group["dates"] if value)
        output.append({
            "manufacturer_relationship_id": _relationship_id(
                key[0], key[1], key[2], key[3]
            ),
            "party_role": key[0],
            "party_name": party_name,
            "organisation_entity_id": entity_id,
            "target_account_id": target_account_id,
            "country": _text(group["country"]),
            "manufacturer_name": _text(group["manufacturer_name"]),
            "manufacturer_entity_id": _text(group["manufacturer_entity_id"]),
            "product_families": _join(group["families"]),
            "models": _join(group["models"]),
            "procurement_event_count": str(event_count),
            "observed_award_count": str(awards),
            "specified_notice_count": str(notices),
            "explicit_preference_count": str(preferences),
            "model_specification_count": str(models),
            "first_evidence_date": dates[0] if dates else "",
            "latest_evidence_date": dates[-1] if dates else "",
            "tender_references": _join(group["references"]),
            "procurement_event_ids": _join(group["events"]),
            "iati_project_ids": _join(group["projects"]),
            "source_urls": _join(group["urls"]),
            "relationship_signal": signal,
            "preference_status": preference_status,
            "relationship_confidence": f"{confidence:.1f}",
            "recommended_action": action,
            "source_layer": "intelligence",
        })
    return sorted(
        output,
        key=lambda row: (
            -float(row["relationship_confidence"]),
            -int(row["observed_award_count"]),
            row["party_name"].casefold(),
            row["manufacturer_name"].casefold(),
        ),
    )


def write_relationships(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build evidence-led manufacturer relationships.")
    parser.add_argument("--matches", default="data/procurement_product_matches.csv")
    parser.add_argument("--events", default="data/procurement_events.csv")
    parser.add_argument("--opportunities", default="data/opportunities.csv")
    parser.add_argument("--buyers", default="data/procurement_buyer_history.csv")
    parser.add_argument("--resolutions", default="data/opportunity_organisation_resolution.csv")
    parser.add_argument("--accounts", default="data/target_accounts.csv")
    parser.add_argument("--manufacturers", default="data/manufacturer_entities.csv")
    parser.add_argument("--world-bank-projects", default="data/world_bank_project_metadata.csv")
    parser.add_argument("--document-evidence", default="data/procurement_document_evidence.csv")
    parser.add_argument("--output", default="data/procurement_manufacturer_relationships.csv")
    args = parser.parse_args()
    rows = build_manufacturer_relationships(
        _read(Path(args.matches)), _read(Path(args.events)),
        _read(Path(args.opportunities)), _read(Path(args.buyers)),
        _read(Path(args.resolutions)), _read(Path(args.accounts)),
        _read(Path(args.manufacturers)), _read(Path(args.world_bank_projects)),
        _read(Path(args.document_evidence)),
    )
    write_relationships(Path(args.output), rows)
    explicit = sum(row["preference_status"] == "EXPLICIT_SOURCE_PREFERENCE" for row in rows)
    awards = sum(int(row["observed_award_count"]) > 0 for row in rows)
    print(f"Manufacturer relationships completed: {len(rows)} relationships, {awards} award-backed, {explicit} explicitly preferred")


if __name__ == "__main__":
    main()
