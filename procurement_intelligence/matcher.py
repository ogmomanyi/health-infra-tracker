import re
from difflib import SequenceMatcher

_STOPWORDS = {
    "and", "the", "for", "with", "from", "into", "project", "programme",
    "program", "health", "strengthening", "support", "development",
}


def _tokens(value):
    return {
        token
        for token in re.findall(r"[a-z0-9]+", (value or "").lower())
        if token not in _STOPWORDS
    }


def similarity(left, right):
    """Return a blended lexical similarity score from 0 to 100."""
    if not left or not right:
        return 0.0
    sequence = SequenceMatcher(None, left.lower(), right.lower()).ratio()
    a, b = _tokens(left), _tokens(right)
    overlap = len(a & b) / max(len(a | b), 1)
    return round((sequence * 0.55 + overlap * 0.45) * 100, 1)


def _contains_country(event_country, project_countries):
    if not event_country or not project_countries:
        return False
    wanted = event_country.strip().lower()
    values = re.split(r"[;,|]", project_countries)
    return any(wanted == value.strip().lower() for value in values if value.strip())


def _equipment_overlap(event, project):
    event_values = _tokens(
        " ".join([
            str(getattr(event, "equipment_category", "") or ""),
            str(getattr(event, "product_family", "") or ""),
        ])
    )
    project_values = _tokens(
        " ".join([
            str(project.get("equipment_target_summary", "") or ""),
            str(project.get("equipment_target_categories", "") or ""),
            str(project.get("product_family", "") or ""),
        ])
    )
    return bool(event_values & project_values)


def match_event(event, projects, threshold=65.0):
    """Match one external procurement event to an IATI project using evidence only.

    Country and equipment evidence are supporting signals only. They cannot
    create a match without meaningful title or buyer evidence. The existing
    opportunity score is never modified.
    """
    explicit_iati = getattr(event, "matched_iati_identifier", "") or ""
    if explicit_iati:
        for project in projects:
            if project.get("iati_identifier") == explicit_iati:
                return {
                    "matched_iati_identifier": explicit_iati,
                    "match_confidence": 100.0,
                    "match_status": "CONFIRMED",
                }

    best = None
    for project in projects:
        title_score = similarity(event.title, project.get("project_title", ""))
        buyer_score = similarity(event.buyer, project.get("funding_agencies", ""))
        country_match = _contains_country(event.country, project.get("country_names", ""))
        equipment_match = _equipment_overlap(event, project)

        score = round(
            title_score * 0.65
            + buyer_score * 0.20
            + (10.0 if country_match else 0.0)
            + (5.0 if equipment_match else 0.0),
            1,
        )

        meaningful_text = title_score >= 55.0 or buyer_score >= 70.0
        if not meaningful_text:
            continue

        candidate = {
            "iati_identifier": project.get("iati_identifier", ""),
            "score": score,
            "country_match": country_match,
            "equipment_match": equipment_match,
            "title_score": title_score,
            "buyer_score": buyer_score,
        }
        if best is None or candidate["score"] > best["score"]:
            best = candidate

    if not best or best["score"] < threshold:
        return {
            "matched_iati_identifier": "",
            "match_confidence": best["score"] if best else 0.0,
            "match_status": "UNMATCHED",
        }

    return {
        "matched_iati_identifier": best["iati_identifier"],
        "match_confidence": best["score"],
        "match_status": "CONFIRMED" if best["score"] >= 85 else "POSSIBLE",
    }
