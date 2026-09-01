import re
from difflib import SequenceMatcher


def _tokens(value):
    return set(re.findall(r"[a-z0-9]+", (value or "").lower()))


def similarity(left, right):
    if not left or not right:
        return 0.0
    sequence = SequenceMatcher(None, left.lower(), right.lower()).ratio()
    a, b = _tokens(left), _tokens(right)
    overlap = len(a & b) / max(len(a | b), 1)
    return round((sequence * 0.55 + overlap * 0.45) * 100, 1)


def match_event(event, projects, threshold=65.0):
    """Return the best project match without altering the existing opportunity score."""
    best = None
    for project in projects:
        title_score = similarity(event.title, project.get("project_title", ""))
        buyer_score = similarity(event.buyer, project.get("funding_agencies", ""))
        country_score = 15.0 if event.country and event.country.lower() in (project.get("country_names", "") or "").lower() else 0.0
        score = round(title_score * 0.65 + buyer_score * 0.20 + country_score, 1)
        if best is None or score > best["score"]:
            best = {"iati_identifier": project.get("iati_identifier", ""), "score": score}

    if not best or best["score"] < threshold:
        return {"matched_iati_identifier": "", "match_confidence": best["score"] if best else 0.0, "match_status": "UNMATCHED"}
    status = "CONFIRMED" if best["score"] >= 85 else "POSSIBLE"
    return {"matched_iati_identifier": best["iati_identifier"], "match_confidence": best["score"], "match_status": status}
