-- =====================================================
-- Organisation Entities
-- Canonical organisation registry
-- =====================================================

DROP TABLE IF EXISTS organisation_entities;

CREATE TABLE organisation_entities (

    entity_id TEXT PRIMARY KEY,

    canonical_name TEXT NOT NULL UNIQUE,

    organisation_type TEXT,

    entity_status TEXT DEFAULT 'ACTIVE',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_org_type
ON organisation_entities(organisation_type);

CREATE INDEX idx_org_status
ON organisation_entities(entity_status);