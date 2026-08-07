-- =====================================================
-- Organisation Resolution Log
-- Audit trail for entity resolution decisions
-- =====================================================

DROP TABLE IF EXISTS organisation_resolution_log;

CREATE TABLE organisation_resolution_log (

    resolution_id TEXT PRIMARY KEY,

    alias_id TEXT NOT NULL,

    entity_id TEXT NOT NULL,

    resolution_action TEXT NOT NULL,

    resolution_rule TEXT,

    confidence_score REAL,

    resolved_by TEXT DEFAULT 'SYSTEM',

    resolution_notes TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (alias_id)
        REFERENCES organisation_aliases(alias_id),

    FOREIGN KEY (entity_id)
        REFERENCES organisation_entities(entity_id)
);

CREATE INDEX idx_resolution_alias
ON organisation_resolution_log(alias_id);

CREATE INDEX idx_resolution_entity
ON organisation_resolution_log(entity_id);

CREATE INDEX idx_resolution_action
ON organisation_resolution_log(resolution_action);