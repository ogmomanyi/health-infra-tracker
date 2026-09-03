"""Validate IATI tender predictions against externally observed procurement notices.

The validator is intentionally conservative: only procurement notices linked to an
IATI activity through the existing evidence-only matcher are used. Confirmed links
provide validation evidence; possible links are retained as supporting signals but
never treated as confirmed outcomes.
"""

from __future__ import annotations

import csv
import math
from datetime import date
from pathlib import Path


CONFIRMED_MATCHES = {"CONFIRMED"}
POSSIBLE_MATCHES = {"POSSIBLE"}


def _text(value: object) -> str:
    value = "" if value is None else str(value)
    value = value.strip()
    if value.lower() in {"nan", "none", "nat"}:
        return ""
    return value


def _parse_date(value: object) -> date | None:
    text = _text(value)
    if not text:
        return None
    # Accept full ISO dates as well as prediction values that begin with YYYY-MM-DD.
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _days_between(left: date, right: date) -> int:
    return abs((left - right).days)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _group_events(events: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for event in events:
        identifier = _text(event.get("matched_iati_identifier"))
        if not identifier:
            continue
        if _text(event.get("match_status")) not in (CONFIRMED_MATCHES | POSSIBLE_MATCHES):
            continue
        grouped.setdefault(identifier, []).append(event)
    return grouped


def validate_predictions(predictions: list[dict[str, str]], events: list[dict[str, str]]) -> list[dict[str, object]]:
    """Return one validation record per IATI tender prediction."""
    events_by_iati = _group_events(events)
    rows: list[dict[str, object]] = []

    for prediction in predictions:
        identifier = _text(prediction.get("iati_identifier"))
        predicted_window = _text(prediction.get("tender_window"))
        predicted_date = _parse_date(predicted_window)
        linked = events_by_iati.get(identifier, [])
        confirmed = [e for e in linked if _text(e.get("match_status")) in CONFIRMED_MATCHES]
        possible = [e for e in linked if _text(e.get("match_status")) in POSSIBLE_MATCHES]

        observed_dates = []
        for event in confirmed + possible:
            published = _parse_date(event.get("publication_date"))
            closing = _parse_date(event.get("closing_date"))
            if published:
                observed_dates.append(published)
            elif closing:
                observed_dates.append(closing)

        nearest_delta = math.inf
        nearest_date: date | None = None
        if predicted_date and observed_dates:
            nearest_date = min(observed_dates, key=lambda observed: _days_between(predicted_date, observed))
            nearest_delta = _days_between(predicted_date, nearest_date)

        if confirmed and predicted_date and nearest_date is not None:
            validation_status = (
                "VALIDATED_ON_TIME" if nearest_delta <= 180 else "OBSERVED_OUTSIDE_WINDOW"
            )
        elif confirmed:
            validation_status = "VALIDATED_NO_DATED_PREDICTION"
        elif possible:
            validation_status = "POSSIBLE_EXTERNAL_SIGNAL"
        elif predicted_date:
            validation_status = "NO_EXTERNAL_EVIDENCE"
        else:
            validation_status = "NO_DATED_PREDICTION"

        rows.append({
            "iati_identifier": identifier,
            "project_title": _text(prediction.get("project_title")),
            "country_codes": _text(prediction.get("country_codes")),
            "predicted_tender_window": predicted_window,
            "predicted_tender_date": predicted_date.isoformat() if predicted_date else "",
            "tender_probability": _text(prediction.get("tender_probability")),
            "tender_stage": _text(prediction.get("tender_stage")),
            "external_notice_count": len(linked),
            "confirmed_notice_count": len(confirmed),
            "possible_notice_count": len(possible),
            "first_observed_notice_date": min(observed_dates).isoformat() if observed_dates else "",
            "nearest_observed_notice_date": nearest_date.isoformat() if nearest_date else "",
            "window_error_days": int(nearest_delta) if math.isfinite(nearest_delta) else "",
            "validation_status": validation_status,
        })

    return rows


def write_validation(path: Path, rows: list[dict[str, object]]) -> None:
    fields = [
        "iati_identifier", "project_title", "country_codes", "predicted_tender_window",
        "predicted_tender_date", "tender_probability", "tender_stage",
        "external_notice_count", "confirmed_notice_count", "possible_notice_count",
        "first_observed_notice_date", "nearest_observed_notice_date", "window_error_days",
        "validation_status",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Validate tender predictions against external procurement events.")
    parser.add_argument("--predictions", default="data/tender_predictions.csv")
    parser.add_argument("--events", default="data/procurement_events.csv")
    parser.add_argument("--output", default="data/tender_prediction_validation.csv")
    args = parser.parse_args()

    predictions = _read_csv(Path(args.predictions))
    events = _read_csv(Path(args.events))
    rows = validate_predictions(predictions, events)
    write_validation(Path(args.output), rows)

    validated = sum(row["validation_status"] == "VALIDATED_ON_TIME" for row in rows)
    possible = sum(row["validation_status"] == "POSSIBLE_EXTERNAL_SIGNAL" for row in rows)
    observed = sum(row["external_notice_count"] > 0 for row in rows)
    print(f"Tender prediction validation completed: {len(rows)} predictions, {observed} with external evidence, {validated} validated on time, {possible} possible signals")


if __name__ == "__main__":
    main()
