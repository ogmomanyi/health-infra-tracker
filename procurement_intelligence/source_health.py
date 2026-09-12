"""Operational source-quality checks for procurement ingestion."""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path

from .evidence import decode_document_urls


FIELDS = [
    "source", "current_run_status", "record_count", "active_opportunity_count", "tender_reference_pct",
    "source_url_pct", "publication_date_pct", "closing_date_pct", "buyer_pct",
    "notice_text_pct", "document_link_pct", "product_match_count",
    "manufacturer_match_count", "health_status", "health_issues",
]


def _read(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _pct(rows: list[dict[str, str]], field: str) -> str:
    if not rows:
        return "0.0"
    present = sum(bool(str(row.get(field) or "").strip()) for row in rows)
    return f"{100 * present / len(rows):.1f}"


def _document_pct(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "0.0"
    present = sum(bool(decode_document_urls(row.get("document_urls"))) for row in rows)
    return f"{100 * present / len(rows):.1f}"


def build_source_health(
    events: list[dict[str, str]],
    matches: list[dict[str, str]],
    *,
    required_sources: list[str] | None = None,
    collection_rows: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for event in events:
        grouped[str(event.get("source") or "Unknown").strip() or "Unknown"].append(event)
    for source in required_sources or []:
        grouped.setdefault(source, [])
    collection = {
        str(row.get("source") or "").strip(): str(row.get("run_status") or "").strip()
        for row in collection_rows or []
    }

    product_events: dict[str, set[str]] = defaultdict(set)
    manufacturer_events: dict[str, set[str]] = defaultdict(set)
    for match in matches:
        source = str(match.get("source") or "Unknown").strip() or "Unknown"
        event_id = str(match.get("procurement_event_id") or "")
        if match.get("product_family"):
            product_events[source].add(event_id)
        if match.get("manufacturer_names"):
            manufacturer_events[source].add(event_id)

    output: list[dict[str, str]] = []
    for source in sorted(grouped):
        rows = grouped[source]
        issues: list[str] = []
        run_status = collection.get(source, "NOT_RECORDED")
        if run_status in {"FAILED", "PARTIAL"}:
            status = "FAILED"
            issues.append(
                "current source run returned no records"
                if run_status == "FAILED"
                else "current source run completed only partially"
            )
        elif not rows:
            status = "FAILED"
            issues.append("no records collected")
        else:
            if float(_pct(rows, "source_url")) < 90:
                issues.append("low source URL completeness")
            if float(_pct(rows, "tender_reference")) < 50:
                issues.append("low tender reference completeness")
            if float(_pct(rows, "publication_date")) < 50:
                issues.append("low publication date completeness")
            status = "REVIEW" if issues else "HEALTHY"
        output.append({
            "source": source,
            "current_run_status": run_status,
            "record_count": str(len(rows)),
            "active_opportunity_count": str(sum(
                row.get("opportunity_status") == "ACTIVE_OPPORTUNITY" for row in rows
            )),
            "tender_reference_pct": _pct(rows, "tender_reference"),
            "source_url_pct": _pct(rows, "source_url"),
            "publication_date_pct": _pct(rows, "publication_date"),
            "closing_date_pct": _pct(rows, "closing_date"),
            "buyer_pct": _pct(rows, "buyer"),
            "notice_text_pct": _pct(rows, "notice_text"),
            "document_link_pct": _document_pct(rows),
            "product_match_count": str(len(product_events[source])),
            "manufacturer_match_count": str(len(manufacturer_events[source])),
            "health_status": status,
            "health_issues": "; ".join(issues),
        })
    return output


def write_source_health(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def sync_manifest(manifest_path: Path, data_dir: Path) -> None:
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    names = (
        "procurement_events", "procurement_processes", "procurement_releases",
        "procurement_documents", "procurement_document_evidence",
        "procurement_line_items", "procurement_product_matches",
        "procurement_manufacturer_relationships",
        "world_bank_project_metadata",
        "procurement_source_collection", "procurement_source_health",
    )
    for name in names:
        path = data_dir / f"{name}.csv"
        if not path.exists():
            continue
        manifest.setdefault("row_counts", {})[name] = len(_read(path))
        manifest.setdefault("files", {})[name] = path.name
    try:
        from intelligence_builder import (
            LAYER_OUTPUTS,
            PIPELINE_LAYERS,
            PIPELINE_VERSION,
            PLAN_PROGRESS,
        )
    except ImportError:
        pass
    else:
        manifest["pipeline_version"] = PIPELINE_VERSION
        manifest["pipeline_layers"] = PIPELINE_LAYERS
        manifest["layer_outputs"] = LAYER_OUTPUTS
        manifest["plan_progress"] = PLAN_PROGRESS
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    summary_path = data_dir / "market_summary.json"
    if summary_path.exists() and "PIPELINE_VERSION" in locals():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["pipeline_version"] = PIPELINE_VERSION
        summary["pipeline_layers"] = PIPELINE_LAYERS
        layer_counts = summary.setdefault("layer_counts", {})
        for layer in PIPELINE_LAYERS:
            layer_counts[layer["layer"].lower()] = {
                dataset: manifest.get("row_counts", {}).get(dataset, 0)
                for dataset in layer["datasets"]
            }
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Check procurement source coverage and quality.")
    parser.add_argument("--events", default="data/procurement_events.csv")
    parser.add_argument("--matches", default="data/procurement_product_matches.csv")
    parser.add_argument("--output", default="data/procurement_source_health.csv")
    parser.add_argument("--collection", default="data/procurement_source_collection.csv")
    parser.add_argument("--require-source", action="append", default=[])
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--manifest", default="data/manifest.json")
    args = parser.parse_args()
    rows = build_source_health(
        _read(Path(args.events)),
        _read(Path(args.matches)),
        required_sources=args.require_source,
        collection_rows=_read(Path(args.collection)),
    )
    write_source_health(Path(args.output), rows)
    sync_manifest(Path(args.manifest), Path(args.output).parent)
    failed = [row["source"] for row in rows if row["health_status"] == "FAILED"]
    print(f"Procurement source health written for {len(rows)} sources; failed: {', '.join(failed) or 'none'}")
    if args.strict and failed:
        raise SystemExit(f"Required procurement sources failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
