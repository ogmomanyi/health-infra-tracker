"""Enrich generated opportunity scores with historical Faram familiarity.

This is a post-processing layer so the core IATI scoring logic remains stable.
Historical evidence is additive only and can never establish current Faram
representation.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from procurement_intelligence.historical_quote_intelligence import load_evidence, familiarity_match


def enrich(opportunities: pd.DataFrame, evidence_rows: list[dict[str, str]]) -> pd.DataFrame:
    if opportunities.empty:
        return opportunities.copy()

    output = opportunities.copy()
    results = output.apply(
        lambda row: pd.Series(
            familiarity_match(
                row.get("project_title"),
                row.get("description"),
                row.get("direct_equipment_categories") or row.get("equipment_target_summary"),
                row.get("manufacturer_mentions"),
                evidence_rows,
            )
        ),
        axis=1,
    )
    output = pd.concat([output, results], axis=1)

    # Historical familiarity is deliberately capped at 10 points. This is a
    # commercial familiarity signal, not a replacement for funding or demand.
    output["opportunity_score_pre_history"] = pd.to_numeric(
        output.get("opportunity_score", 0), errors="coerce"
    ).fillna(0)
    output["opportunity_score"] = (
        output["opportunity_score_pre_history"]
        + pd.to_numeric(output["historical_familiarity_score"], errors="coerce").fillna(0)
    ).clip(upper=100).round(1)

    def band(score: float) -> str:
        if score >= 75:
            return "Strategic Priority"
        if score >= 60:
            return "Qualified Lead"
        if score >= 40:
            return "Watchlist"
        return "Long Range"

    output["priority_band"] = output["opportunity_score"].apply(band)
    output["signal_summary"] = output.apply(
        lambda row: "; ".join(
            value for value in [
                str(row.get("signal_summary") or "").strip(),
                (
                    "historical Faram commercial familiarity"
                    if float(row.get("historical_familiarity_score") or 0) > 0
                    else ""
                ),
            ]
            if value
        ),
        axis=1,
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Add historical Faram familiarity to opportunities.")
    parser.add_argument("--input", default="data/opportunities.csv")
    parser.add_argument("--evidence", default="data/faram_historical_quote_evidence.csv")
    parser.add_argument("--output", default="data/opportunities.csv")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    opportunities = pd.read_csv(input_path, dtype=str, keep_default_na=False) if input_path.exists() else pd.DataFrame()
    evidence = load_evidence(Path(args.evidence))
    enriched = enrich(opportunities, evidence)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    enriched.to_csv(output_path, index=False)
    print(f"Historical familiarity enrichment completed: {len(enriched)} opportunities")


if __name__ == "__main__":
    main()
