import sqlite3
import unittest

from procurement_intelligence.supplier_resolution import (
    ensure_supplier_registry,
    load_supplier_candidates,
    resolve_supplier,
    seed_explicit_suppliers,
    supplier_entity_id,
    supplier_key,
)


class SupplierResolutionTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(
            """
            CREATE TABLE supplier_entities (
                entity_id TEXT PRIMARY KEY,
                canonical_name TEXT NOT NULL UNIQUE,
                supplier_type TEXT,
                country TEXT,
                entity_status TEXT DEFAULT 'ACTIVE'
            );
            CREATE TABLE supplier_aliases (
                alias_id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                alias_name TEXT NOT NULL,
                supplier_country TEXT,
                source_system TEXT NOT NULL DEFAULT 'PROCUREMENT',
                is_primary_alias INTEGER DEFAULT 0,
                match_method TEXT NOT NULL,
                confidence_score REAL
            );
            INSERT INTO supplier_entities VALUES ('SUP-001', 'EGIS Kenya Limited', 'COMPANY', 'Kenya', 'ACTIVE');
            INSERT INTO supplier_entities VALUES ('SUP-002', 'Acme Medical Ltd', 'COMPANY', 'Kenya', 'ACTIVE');
            INSERT INTO supplier_aliases VALUES ('ALIAS-001', 'SUP-001', 'EGIS KENYA', 'Kenya', 'WORLD_BANK', 0, 'MANUAL', 1.0);
            """
        )

    def tearDown(self):
        self.conn.close()

    def test_normalization_is_deterministic(self):
        self.assertEqual(supplier_key("ÉGIS Kenya, Ltd."), "egis kenya ltd")

    def test_entity_id_is_deterministic(self):
        self.assertEqual(supplier_entity_id("egis kenya ltd"), supplier_entity_id("egis kenya ltd"))

    def test_canonical_exact_match(self):
        result = resolve_supplier("EGIS Kenya Limited", "Kenya", load_supplier_candidates(self.conn))
        self.assertEqual(result.entity_id, "SUP-001")
        self.assertEqual(result.canonical_name, "EGIS Kenya Limited")
        self.assertEqual(result.match_method, "CANONICAL_EXACT")
        self.assertEqual(result.confidence_score, 1.0)

    def test_alias_exact_match(self):
        result = resolve_supplier("EGIS KENYA", "Kenya", load_supplier_candidates(self.conn))
        self.assertEqual(result.entity_id, "SUP-001")
        self.assertEqual(result.canonical_name, "EGIS Kenya Limited")
        self.assertEqual(result.match_method, "ALIAS_EXACT")

    def test_unknown_supplier_is_not_fuzzy_matched(self):
        result = resolve_supplier("EGIS Kenya Ltd", "Kenya", load_supplier_candidates(self.conn))
        self.assertIsNone(result.entity_id)
        self.assertEqual(result.match_method, "UNRESOLVED")

    def test_ambiguous_alias_is_excluded(self):
        self.conn.execute("INSERT INTO supplier_entities VALUES ('SUP-003', 'Global Diagnostics', 'COMPANY', 'Uganda', 'ACTIVE')")
        self.conn.execute("INSERT INTO supplier_aliases VALUES ('ALIAS-002', 'SUP-001', 'GLOBAL MEDICAL', 'Kenya', 'WORLD_BANK', 0, 'MANUAL', 1.0)")
        self.conn.execute("INSERT INTO supplier_aliases VALUES ('ALIAS-003', 'SUP-003', 'GLOBAL MEDICAL', 'Uganda', 'WORLD_BANK', 0, 'MANUAL', 1.0)")
        self.conn.commit()
        result = resolve_supplier("GLOBAL MEDICAL", candidates=load_supplier_candidates(self.conn))
        self.assertIsNone(result.entity_id)
        self.assertEqual(result.match_method, "UNRESOLVED")

    def test_registry_seeding_is_idempotent_and_non_fuzzy(self):
        conn = sqlite3.connect(":memory:")
        try:
            ensure_supplier_registry(conn)
            first = seed_explicit_suppliers(conn, [("Acme Medical Ltd", "Kenya"), ("ACME MEDICAL LTD", "Kenya")])
            second = seed_explicit_suppliers(conn, [("Acme Medical Ltd", "Kenya")])
            self.assertEqual(first, 1)
            self.assertEqual(second, 0)
            rows = conn.execute("SELECT entity_id, canonical_name FROM supplier_entities").fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], supplier_entity_id("acme medical ltd"))
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
