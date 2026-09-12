import re
from collections import defaultdict
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
_BLOCKING_STOPWORDS = _STOPWORDS | {
    "acquisition", "bid", "bids", "goods", "invitation", "notice",
    "procurement", "services", "supply", "tender", "works", "equipment",
}


def _tokens(value):
    return {
        token for token in re.findall(r"[a-z0-9]+", (value or "").lower())
        if token not in _STOPWORDS
    }


def _blocking_tokens(value):
    return {
        token for token in re.findall(r"[a-z0-9]+", (value or "").lower())
        if token not in _BLOCKING_STOPWORDS and len(token) >= 3
    }


def similarity(left, right):
    if not left or not right:
        return 0.0
    left_lower = left.lower()
    right_lower = right.lower()
    shorter, longer = sorted((left_lower, right_lower), key=len)
    if shorter in longer:
        sequence = 1.0
    elif len(left_lower) * len(right_lower) > 100_000:
        sequence = 0.0
    else:
        sequence = SequenceMatcher(None, left_lower, right_lower).ratio()
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


class ProjectMatcher:
    """Reusable candidate index for matching many notices to one IATI snapshot."""

    def __init__(self, projects):
        self.projects = list(projects)
        self.prepared = []
        self.identifiers: dict[str, int] = {}
        self.references: dict[str, set[int]] = defaultdict(set)
        self.title_index: dict[str, set[int]] = defaultdict(set)
        self.buyer_index: dict[str, set[int]] = defaultdict(set)
        self.country_index: dict[str, set[int]] = defaultdict(set)
        reference_fields = (
            "project_reference", "project_id", "reference", "activity_ref",
            "external_project_id", "programme_reference", "iati_identifier",
        )
        for index, project in enumerate(self.projects):
            title_text = _project_text(project)
            buyer_text = _buyer_text(project)
            title_tokens = _tokens(title_text)
            buyer_tokens = _tokens(buyer_text)
            equipment_tokens = _tokens(" ".join(str(project.get(field, "") or "") for field in (
                "equipment_target_summary", "equipment_target_categories", "product_family",
            )))
            countries = {
                _country_key(value)
                for value in re.split(r"[;,|]", str(project.get("country_names", "") or ""))
                if value.strip()
            }
            self.prepared.append({
                "project": project,
                "title_text": title_text,
                "buyer_text": buyer_text,
                "title_tokens": title_tokens,
                "buyer_tokens": buyer_tokens,
                "equipment_tokens": equipment_tokens,
                "countries": countries,
            })
            identifier = str(project.get("iati_identifier") or "").strip()
            if identifier:
                self.identifiers[identifier] = index
            for field in reference_fields:
                value = str(project.get(field) or "").strip().lower()
                if not value:
                    continue
                self.references[value].add(index)
                for token in re.split(r"[-_/]", value):
                    if len(token) >= 4:
                        self.references[token].add(index)
            for token in _blocking_tokens(title_text):
                self.title_index[token].add(index)
            for token in _blocking_tokens(buyer_text):
                self.buyer_index[token].add(index)
            for country in countries:
                self.country_index[country].add(index)

    def _candidates(self, event, limit=40):
        event_title_tokens = _tokens(getattr(event, "title", "") or "")
        event_buyer_tokens = _tokens(getattr(event, "buyer", "") or "")
        event_equipment_tokens = _tokens(" ".join([
            str(getattr(event, "equipment_category", "") or ""),
            str(getattr(event, "product_family", "") or ""),
            str(getattr(event, "title", "") or ""),
        ]))
        title_blocking = _blocking_tokens(getattr(event, "title", "") or "")
        buyer_blocking = _blocking_tokens(getattr(event, "buyer", "") or "")
        country = _country_key(getattr(event, "country", "") or "")
        indices: set[int] = set()
        for token in title_blocking:
            indices.update(self.title_index.get(token, ()))
        for token in buyer_blocking:
            indices.update(self.buyer_index.get(token, ()))
        if country:
            indices.update(self.country_index.get(country, ()))

        ranked = []
        for index in indices:
            prepared = self.prepared[index]
            title_overlap = len(event_title_tokens & prepared["title_tokens"])
            buyer_overlap = len(event_buyer_tokens & prepared["buyer_tokens"])
            country_match = bool(country and country in prepared["countries"])
            equipment_match = bool(event_equipment_tokens & prepared["equipment_tokens"])
            if not (title_overlap or buyer_overlap or country_match and equipment_match):
                continue
            blocking_score = (
                title_overlap * 4 + buyer_overlap * 5
                + (2 if country_match else 0) + (2 if equipment_match else 0)
            )
            ranked.append((blocking_score, index, country_match, equipment_match))
        ranked.sort(reverse=True)
        return ranked[:limit]

    def match(self, event, threshold=65.0):
        explicit_iati = getattr(event, "matched_iati_identifier", "") or ""
        if explicit_iati and explicit_iati in self.identifiers:
            return {
                "matched_iati_identifier": explicit_iati,
                "match_confidence": 100.0,
                "match_status": "CONFIRMED",
            }

        reference = (getattr(event, "project_reference", "") or "").strip().lower()
        if reference:
            exact_indices = self.references.get(reference, set())
            exact = [
                self.projects[index] for index in exact_indices
                if _exact_project_reference(event, self.projects[index])
            ]
            identifiers = {
                str(project.get("iati_identifier") or "") for project in exact
                if project.get("iati_identifier")
            }
            if len(identifiers) == 1:
                return {
                    "matched_iati_identifier": identifiers.pop(),
                    "match_confidence": 100.0,
                    "match_status": "CONFIRMED",
                }
            return {
                "matched_iati_identifier": "",
                "match_confidence": 0.0,
                "match_status": "UNMATCHED",
            }

        best = None
        second = None
        for _, index, country_match, equipment_match in self._candidates(event):
            prepared = self.prepared[index]
            project = prepared["project"]
            title_score = similarity(event.title, prepared["title_text"])
            buyer_score = similarity(event.buyer, prepared["buyer_text"])
            score = round(
                title_score * 0.55
                + buyer_score * 0.20
                + (15.0 if country_match else 0.0)
                + (10.0 if equipment_match else 0.0),
                1,
            )
            if not (
                title_score >= 45.0
                or buyer_score >= 70.0
                or country_match and equipment_match
            ):
                continue
            candidate = {"iati_identifier": project.get("iati_identifier", ""), "score": score}
            if best is None or score > best["score"]:
                second = best
                best = candidate
            elif second is None or score > second["score"]:
                second = candidate

        if not best or best["score"] < threshold:
            return {
                "matched_iati_identifier": "",
                "match_confidence": best["score"] if best else 0.0,
                "match_status": "UNMATCHED",
            }
        if second and best["score"] - second["score"] < 5.0:
            return {
                "matched_iati_identifier": "",
                "match_confidence": best["score"],
                "match_status": "UNMATCHED",
            }
        return {
            "matched_iati_identifier": best["iati_identifier"],
            "match_confidence": best["score"],
            "match_status": "CONFIRMED" if best["score"] >= 85 else "POSSIBLE",
        }


def match_event(event, projects, threshold=65.0):
    """Match an external procurement event to IATI using explicit evidence only."""
    matcher = projects if isinstance(projects, ProjectMatcher) else ProjectMatcher(projects)
    return matcher.match(event, threshold=threshold)
