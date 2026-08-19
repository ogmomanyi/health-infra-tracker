-- =====================================================
-- Organisation Aliases
-- Maps raw organisation identities to canonical entities
-- =====================================================

DROP TABLE IF EXISTS organisation_aliases;

CREATE TABLE organisation_aliases (

    alias_id TEXT PRIMARY KEY,

    entity_id TEXT NOT NULL,

    organisation_key TEXT NOT NULL,

    org_ref TEXT,

    alias_name TEXT NOT NULL,

    source_system TEXT NOT NULL DEFAULT 'IATI',

    is_primary_alias INTEGER DEFAULT 0,

    match_method TEXT NOT NULL,

    confidence_score REAL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (entity_id)
        REFERENCES organisation_entities(entity_id)
);

CREATE INDEX idx_alias_entity
ON organisation_aliases(entity_id);

CREATE INDEX idx_alias_org_key
ON organisation_aliases(organisation_key);

CREATE INDEX idx_alias_org_ref
ON organisation_aliases(org_ref);

CREATE INDEX idx_alias_name
ON organisation_aliases(alias_name);

CREATE INDEX idx_alias_match_method
ON organisation_aliases(match_method);