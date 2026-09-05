-- =====================================================
-- Supplier Aliases
-- Raw supplier names mapped to canonical supplier entities
-- =====================================================

DROP TABLE IF EXISTS supplier_aliases;

CREATE TABLE supplier_aliases (
    alias_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    alias_name TEXT NOT NULL,
    supplier_country TEXT,
    source_system TEXT NOT NULL DEFAULT 'PROCUREMENT',
    is_primary_alias INTEGER DEFAULT 0,
    match_method TEXT NOT NULL,
    confidence_score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (entity_id) REFERENCES supplier_entities(entity_id)
);

CREATE INDEX idx_supplier_alias_entity
ON supplier_aliases(entity_id);

CREATE INDEX idx_supplier_alias_name
ON supplier_aliases(alias_name);
