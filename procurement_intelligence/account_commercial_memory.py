"""Build an account-level commercial-memory sidecar from opportunities and Faram evidence.

This intentionally remains separate from target_accounts.csv so historical supplier
activity cannot masquerade as current representation or canonical account data.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from procurement_intelligence.historical_quote_intelligence import familiarity_match


FIELDS = [
    "target_account_id",
    "account_name",
    "organisation_entity_id",
    "commercial_memory_score",
    "commercial_memory_band",
    "commercial_memory_evidence_count",
    "commercial_memory_evidence_ids",
    "commercial_memory_manufacturers",
    "commercial_memory_product_families",
    "catalogue_matched_families",
    "recommended_action",
]


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _split(value: object) -> list[str]:
    return [part.strip() for part in _text(value).split(";") if part.strip()]


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _family_rows(account: dict[str, str], evidence_rows: Iterable[dict[str, str]]):
    families = _split(account.get("top_needs"))
    matched = []
    for family in families:
        for evidence in evidence_rows:
            result = familiarity_match(
                {"product_family": family},
                evidence,
            )
            if result.get("historical_familiarity_score", 0) > 0:
                matched.append((family, evidence, float(result["historical_familiarity_score"])))
    return matched


def build_memory(accounts: list[dict[str, str]], evidence_rows: list[dict[str, str]], catalogue_rows: list[dict[str, str]]):
    active_catalogue_families = {
        _text(row.get("product_family")).lower()
        for row in catalogue_rows
        if _text(row.get("principal_status")).lower() in {"active", "current", "yes", "true"}
    }
    output = []

    for account in accounts:
        matches = _family_rows(account, evidence_rows)
        if not matches:
            output.append({
                "target_account_id": _text(account.get("target_account_id")),
                "account_name": _text(account.get("account_name")),
                "organisation_entity_id": _text(account.get("organisation_entity_id")),
                "commercial_memory_score": "0",
                "commercial_memory_band": "NONE",
                "commercial_memory_evidence_count": "0",
                "commercial_memory_evidence_ids": "",
                "commercial_memory_manufacturers": "",
                "commercial_memory_product_families": "",
                "catalogue_matched_families": "",
                "recommended_action": "No historical Faram product-family familiarity identified; use current opportunity signals.",
            })
            continue

        # Keep the strongest evidence per product family to avoid inflating the score
        # because one family has many old quotations.
        best_by_family: dict[str, tuple[dict[str, str], float]] = {}
        for family, evidence, score in matches:
            key = _text(family).lower()
            current = best_by_family.get(key)
            if current is None or score > current[1]:
                best_by_family[key] = (evidence, score)

        selected = list(best_by_family.values())
        score = min(10.0, sum(item[1] for item in selected))
        band = "HIGH" if score >= 6 else "MEDIUM" if score >= 3 else "LOW"
        evidence_ids = []
        manufacturers = []
        families = []
        catalogue_families = []
        for evidence, _ in selected:
            evidence_ids.append(_text(evidence.get("evidence_id")))
            manufacturers.append(_text(evidence.get("manufacturer_name")))
            families.append(_text(evidence.get("product_family")))
            if _text(evidence.get("product_family")).lower() in active_catalogue_families:
                catalogue_families.append(_text(evidence.get("product_family")))

        action = (
            "Prioritise account engagement around historically familiar product families and verify current principal/territory status."
            if catalogue_families
            else "Use historical product-family familiarity as a qualification signal; verify current principal and territory before pursuit."
        )

        output.append({
            "target_account_id": _text(account.get("target_account_id")),
            "account_name": _text(account.get("account_name")),
            "organisation_entity_id": _text(account.get("organisation_entity_id")),
            "commercial_memory_score": str(round(score, 1)),
            "commercial_memory_band": band,
            "commercial_memory_evidence_count": str(len(evidence_ids)),
            "commercial_memory_evidence_ids": "; ".join(dict.fromkeys(evidence_ids)),
            "commercial_memory_manufacturers": "; ".join(dict.fromkeys(m for m in manufacturers if m)),
            "commercial_memory_product_families": "; ".join(dict.fromkeys(f for f in families if f)),
            "catalogue_matched_families": "; ".join(dict.fromkeys(f for f in catalogue_families if f)),
            "recommended_action": action,
        })

    return output


def write_memory(accounts_path: Path, evidence_path: Path, catalogue_path: Path, output_path: Path) -> int:
    rows = build_memory(
        load_csv(accounts_path),
        load_csv(evidence_path),
        load_csv(catalogue_path),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--accounts", default="data/target_accounts.csv")
    parser.add_argument("--evidence", default="data/faram_historical_quote_evidence.csv")
    parser.add_argument("--catalogue", default="data/faram_product_catalogue.csv")
    parser.add_argument("--output", default="data/faram_account_commercial_memory.csv")
    args = parser.parse_args()
    count = write_memory(Path(args.accounts), Path(args.evidence), Path(args.catalogue), Path(args.output))
    print(f"Faram account commercial memory completed: {count} accounts")


if __name__ == "__main__":
    main()
