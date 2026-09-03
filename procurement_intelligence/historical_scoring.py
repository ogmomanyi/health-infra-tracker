"""Core scoring hook for historical Faram commercial familiarity."""

from __future__ import annotations

from typing import Iterable

from procurement_intelligence.historical_quote_intelligence import (
    enrich_opportunity,
)


def apply_historical_familiarity(
    row,
    score_result: dict[str, object],
    evidence_rows: Iterable[dict[str, str]],
) -> dict[str, object]:
    """Add capped historical familiarity to the existing opportunity score.

    Historical quotation evidence is an additive commercial familiarity signal;
    it never proves current representation, principal status, or territory.
    """
    result = dict(score_result)
    familiarity = enrich_opportunity(row.to_dict() if hasattr(row, "to_dict") else row, evidence_rows)
    familiarity_score = float(familiarity.get("historical_familiarity_score", 0.0) or 0.0)

    base_score = float(result.get("opportunity_score", 0.0) or 0.0)
    final_score = max(0.0, min(100.0, round(base_score + familiarity_score, 1)))
    result["opportunity_score"] = final_score

    signals = str(result.get("signal_summary", "") or "").strip()
    if familiarity_score > 0:
        history_signal = "historical Faram commercial familiarity"
        result["signal_summary"] = "; ".join(
            item for item in [signals, history_signal] if item
        )

    if final_score >= 75:
        result["priority_band"] = "Strategic Priority"
    elif final_score >= 60:
        result["priority_band"] = "Qualified Lead"
    elif final_score >= 40:
        result["priority_band"] = "Watchlist"
    else:
        result["priority_band"] = "Long Range"

    return result
