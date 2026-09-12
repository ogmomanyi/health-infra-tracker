import csv
from pathlib import Path
from tempfile import TemporaryDirectory

from procurement_intelligence.procurement_evidence_view import enrich_accounts, for_account, for_event


def _write(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def test_for_event_joins_process_evidence():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        events = root / "events.csv"; items = root / "items.csv"
        releases = root / "releases.csv"; documents = root / "documents.csv"
        relationships = root / "relationships.csv"
        _write(events, ["procurement_event_id", "procurement_process_id"], [{"procurement_event_id": "E1", "procurement_process_id": "P1"}])
        _write(items, ["procurement_event_id", "product_family"], [{"procurement_event_id": "E1", "product_family": "Centrifuge"}])
        _write(releases, ["procurement_process_id", "observed_at"], [{"procurement_process_id": "P1", "observed_at": "2026-09-10"}, {"procurement_process_id": "P1", "observed_at": "2026-09-12"}])
        _write(documents, ["procurement_process_id", "document_url"], [{"procurement_process_id": "P1", "document_url": "https://example.test/spec.pdf"}])
        _write(relationships, ["procurement_event_ids", "party_role", "manufacturer_name"], [{"procurement_event_ids": "E0; E1", "party_role": "DONOR", "manufacturer_name": "Acme"}])
        payload = for_event("E1", events_path=events, line_items_path=items, releases_path=releases, documents_path=documents, relationships_path=relationships)
        assert payload["line_items"][0]["product_family"] == "Centrifuge"
        assert payload["releases"][0]["observed_at"] == "2026-09-12"
        assert len(payload["documents"]) == 1
        assert payload["manufacturer_relationships"][0]["party_role"] == "DONOR"


def test_account_projection_includes_relationship_only_accounts():
    with TemporaryDirectory() as tmp:
        relationships = Path(tmp) / "relationships.csv"
        _write(relationships, ["target_account_id", "party_name", "party_role", "manufacturer_name"], [{
            "target_account_id": "A1", "party_name": "Ministry of Health",
            "party_role": "RECEIVING_PARTY", "manufacturer_name": "Abbott",
        }])
        accounts = enrich_accounts([], relationships_path=relationships)
        assert accounts[0]["account_name"] == "Ministry of Health"
        assert accounts[0]["manufacturer_relationships"][0]["manufacturer_name"] == "Abbott"
        assert for_account("A1", relationships_path=relationships)[0]["party_role"] == "RECEIVING_PARTY"
