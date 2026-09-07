-- =====================================================
-- Supplier Entities
-- Canonical supplier registry for competitive intelligence
-- =====================================================

DROP TABLE IF EXISTS supplier_entities;

CREATE TABLE supplier_entities (
    entity_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL UNIQUE,
    supplier_type TEXT,
    country TEXT,
    entity_status TEXT DEFAULT 'ACTIVE',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_supplier_entity_status
ON supplier_entities(entity_status);

CREATE INDEX idx_supplier_entity_country
ON supplier_entities(country);
