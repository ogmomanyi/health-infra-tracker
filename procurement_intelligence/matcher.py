import re
from difflib import SequenceMatcher

_STOPWORDS = {
    "and", "the", "for", "with", "from", "into", "project", "programme",
    "program", "health", "strengthening", "support", "development", "implementation",
}
_COUNTRY_ALIASES = {
    "democratic republic of the congo": {"democratic republic of the congo", "congo, democratic republic of the", "drc", "congo dr"},
    "kenya": {"kenya"}, "uganda": {"uganda"}, "rwanda": {"rwanda"},
    "ethiopia": {"ethiopia"}, "somalia": {"somalia"}, "south sudan": {"south sudan"},
}


def _tokens(value):
    return {
        token for token in re.findall(r"[a-z0-9]+", (value or "").lower())
        if token not in _STOPWORDS
    }


def similarity(left, right):
    if not left or not right:
        return 0.0
    sequence = SequenceMatcher(None, left.lower(), right.lower()).ratio()
    a, b = _tokens(left), _tokens(right)
    overlap = len(a & b) / max(len(a | b), 1)
    return round((sequence * 0.45 + overlap * 0.55) * 100, 1)


def _country_key(value):
    wanted = " ".join((value or "").strip().lower().replace("(", " ").replace(")", " ").split())
    for key, aliases in _COUNTRY_ALIASES.items():
        if wanted in aliases:
            return key
    return wanted


def _contains_country(event_country, project_countries):
    if not event_country or not project_countries:
        return False
    wanted = _country_key(event_country)
    values = re.split(r"[;,|]", project_countries)
    return any(wanted == _country_key(value) for value in values if value.strip())


def _equipment_overlap(event, project):
    event_values = _tokens(" ".join([
        str(getattr(event, "equipment_category", "") or ""),
        str(getattr(event, "product_family", "") or ""),
        str(getattr(event, "title", "") or ""),
    ]))
    project_values = _tokens(" ".join([
        str(project.get("equipment_target_summary", "") or ""),
        str(project.get("equipment_target_categories", "") or ""),
        str(project.get("product_family", "") or ""),
    ]))
    return bool(event_values & project_values)


def _project_text(project):
    return " ".join(str(project.get(field, "") or "") for field in (
        "project_title", "activity_title", "project_name", "programme_title",
    ))


def _buyer_text(project):
    return " ".join(str(project.get(field, "") or "") for field in (
        "funding_agencies", "implementing_agencies", "implementing_agency",
        "implementing_partners", "organisations", "organisation_name", "buyer", "client",
    ))


def _exact_project_reference(event, project):
    reference = (getattr(event, "project_reference", "") or "").strip().lower()
    if not reference:
        return False

    for field in ("project_reference", "project_id", "reference", "activity_ref", "external_project_id", "programme_reference"):
        candidate = (project.get(field, "") or "").strip().lower()
        if candidate == reference:
            return True
        if candidate and re.search(rf"(?:^|[-_/]){re.escape(reference)}(?:$|[-_/])", candidate):
            return True

    identifier = (project.get("iati_identifier", "") or "").strip().lower()
    if identifier == reference:
        return True
    return bool(identifier and re.search(rf"(?:^|[-_/]){re.escape(reference)}(?:$|[-_/])", identifier))


def match_event(event, projects, threshold=65.0):
    """Match an external procurement event to IATI using explicit evidence only."""
    explicit_iati = getattr(event, "matched_iati_identifier", "") or ""
    if explicit_iati:
        for project in projects:
            if project.get("iati_identifier") == explicit_iati:
                return {"matched_iati_identifier": explicit_iati, "match_confidence": 100.0, "match_status": "CONFIRMED"}

    for project in projects:
        if _exact_project_reference(event, project):
            identifier = project.get("iati_identifier", "")
            if identifier:
                return {"matched_iati_identifier": identifier, "match_confidence": 100.0, "match_status": "CONFIRMED"}

    best = None
    second = None
    for project in projects:
        title_score = similarity(event.title, _project_text(project))
        buyer_score = similarity(event.buyer, _buyer_text(project))
        country_match = _contains_country(event.country, project.get("country_names", ""))
        equipment_match = _equipment_overlap(event, project)
        score = round(
            title_score * 0.55
            + buyer_score * 0.20
            + (15.0 if country_match else 0.0)
            + (10.0 if equipment_match else 0.0),
            1,
        )
        if not (title_score >= 45.0 or buyer_score >= 70.0 or country_match and equipment_match):
            continue
        candidate = {"iati_identifier": project.get("iati_identifier", ""), "score": score}
        if best is None or score > best["score"]:
            second = best
            best = candidate
        elif second is None or score > second["score"]:
            second = candidate

    if not best or best["score"] < threshold:
        return {"matched_iati_identifier": "", "match_confidence": best["score"] if best else 0.0, "match_status": "UNMATCHED"}

    if second and best["score"] - second["score"] < 5.0:
        return {"matched_iati_identifier": "", "match_confidence": best["score"], "match_status": "UNMATCHED"}

    return {
        "matched_iati_identifier": best["iati_identifier"],
        "match_confidence": best["score"],
        "match_status": "CONFIRMED" if best["score"] >= 85 else "POSSIBLE",
    }
