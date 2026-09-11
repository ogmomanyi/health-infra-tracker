import pandas as pd
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from product_manufacturer_intelligence import (
    build_manufacturer_entities_dataset,
    build_manufacturer_intelligence_dataset,
    build_product_intelligence_dataset,
    refresh_outputs,
)


def frame(rows):
    return pd.DataFrame(rows)


def test_manufacturer_entities_merge_explicit_sources_and_aliases():
    opportunities = frame([{
        "iati_identifier": "IATI-1",
        "manufacturer_mentions": "Thermo Fisher Scientific",
        "equipment_target_summary": "Laboratory Systems",
        "country_codes": "KE",
    }])
    catalogue = frame([{
        "faram_product_id": "F-1",
        "product_name": "Centrifuge",
        "manufacturer_name": "Thermo Scientific",
        "product_family": "Centrifuge",
        "equipment_category": "Centrifuge",
        "principal_status": "pending",
        "territory": "Kenya",
    }])
    entities = build_manufacturer_entities_dataset(opportunities, catalogue=catalogue)

    assert len(entities) == 1
    row = entities.iloc[0]
    assert row["manufacturer_name"] == "Thermo Fisher"
    assert row["activity_count"] == 1
    assert row["catalogue_product_count"] == 1
    assert "Thermo Scientific" in row["manufacturer_aliases"]
    assert "Controlled Faram catalogue" in row["evidence_sources"]


def test_historical_product_never_becomes_current_catalogue_coverage():
    history = frame([{
        "product_family": "Hematology Analyzer",
        "product_name": "HemoScreen Analyzer",
        "manufacturer_name": "PixCell",
        "model": "HemoScreen",
        "historical_quote_count": "2",
        "evidence_strength": "MEDIUM",
    }])
    products = build_product_intelligence_dataset(
        catalogue=frame([]),
        historical_quotes=history,
        procurement_matches=frame([]),
        faram_matches=frame([]),
        product_fit=frame([]),
    )

    assert len(products) == 1
    row = products.iloc[0]
    assert row["catalogue_status"] == "HISTORICAL_ONLY"
    assert row["commercial_position"] == "HISTORICAL_EVIDENCE_ONLY"
    assert row["principal_status"] == "historical"


def test_active_catalogue_and_verified_fit_are_reported_separately():
    catalogue = frame([{
        "faram_product_id": "F-1",
        "product_name": "Analyzer A",
        "manufacturer_name": "Principal A",
        "product_family": "Hematology Analyzer",
        "equipment_category": "Analyzer",
        "model": "A1",
        "principal_status": "active",
        "territory": "Kenya",
        "source": "controlled record",
    }])
    demand = frame([{
        "procurement_event_id": "E-1",
        "product_family": "Hematology Analyzer",
        "match_status": "MATCHED_PRODUCT_FAMILY",
        "manufacturer_names": "",
    }])
    faram_matches = frame([{
        "procurement_event_id": "E-1",
        "faram_product_id": "F-1",
        "match_status": "FARAM_MATCH",
        "match_confidence": "95",
    }])
    fits = frame([{
        "faram_product_id": "F-1",
        "technical_status": "PASS",
    }])
    products = build_product_intelligence_dataset(
        catalogue,
        frame([]),
        demand,
        faram_matches,
        fits,
    )

    row = products.iloc[0]
    assert row["commercial_position"] == "ACTIVE_TENDER_MATCH"
    assert row["family_demand_count"] == 1
    assert row["actionable_match_count"] == 1
    assert row["technical_pass_count"] == 1
    assert row["average_match_confidence"] == 95


def test_manufacturer_intelligence_keeps_pending_principal_in_validation():
    catalogue = frame([{
        "faram_product_id": "F-1",
        "product_name": "Analyzer A",
        "manufacturer_name": "Principal A",
        "product_family": "Hematology Analyzer",
        "equipment_category": "Analyzer",
        "principal_status": "pending",
        "territory": "Kenya",
    }])
    demand = frame([{
        "procurement_event_id": "E-1",
        "product_family": "Hematology Analyzer",
        "match_status": "MATCHED_PRODUCT_FAMILY",
        "manufacturer_names": "",
    }])
    entities = build_manufacturer_entities_dataset(frame([]), catalogue=catalogue)
    products = build_product_intelligence_dataset(catalogue, frame([]), demand, frame([]), frame([]))
    intelligence = build_manufacturer_intelligence_dataset(entities, products, procurement_matches=demand)

    row = intelligence.iloc[0]
    assert row["coverage_status"] == "PRINCIPAL_VALIDATION_REQUIRED"
    assert row["active_product_count"] == 0
    assert row["pending_product_count"] == 1
    assert row["aligned_market_demand_count"] == 1
    assert "Confirm current principal authorization" in row["recommended_action"]


def test_focused_refresh_persists_csv_database_and_metadata():
    with TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        frame([{
            "iati_identifier": "IATI-1",
            "manufacturer_mentions": "Philips",
            "equipment_target_summary": "Imaging",
            "country_codes": "KE",
        }]).to_csv(data_dir / "opportunities.csv", index=False)
        frame([{
            "faram_product_id": "F-1",
            "product_name": "Imaging System",
            "manufacturer_name": "Philips",
            "product_family": "Imaging",
            "equipment_category": "Imaging",
            "principal_status": "active",
            "territory": "Kenya",
        }]).to_csv(data_dir / "faram_product_catalogue.csv", index=False)
        (data_dir / "manifest.json").write_text(
            json.dumps({"row_counts": {}, "files": {}}), encoding="utf-8"
        )
        (data_dir / "market_summary.json").write_text(
            json.dumps({"layer_counts": {}, "metrics": {}}), encoding="utf-8"
        )
        database = data_dir / "intelligence.db"

        datasets = refresh_outputs(data_dir, database)

        assert len(datasets["product_intelligence"]) == 1
        assert len(datasets["manufacturer_intelligence"]) == 1
        assert (data_dir / "product_intelligence.csv").exists()
        manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["row_counts"]["manufacturer_entities"] == 1
        connection = sqlite3.connect(database)
        try:
            assert connection.execute("select count(*) from product_intelligence").fetchone()[0] == 1
        finally:
            connection.close()
