-- =====================================================
-- Organisation Relationships
-- Structural relationships between canonical organisations
-- =====================================================

DROP TABLE IF EXISTS organisation_relationships;

CREATE TABLE organisation_relationships (

    relationship_id TEXT PRIMARY KEY,

    parent_entity_id TEXT NOT NULL,

    child_entity_id TEXT NOT NULL,

    relationship_type TEXT NOT NULL,

    source_system TEXT NOT NULL DEFAULT 'IATI',

    confidence_score REAL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (parent_entity_id)
        REFERENCES organisation_entities(entity_id),

    FOREIGN KEY (child_entity_id)
        REFERENCES organisation_entities(entity_id)
);

CREATE INDEX idx_rel_parent
ON organisation_relationships(parent_entity_id);

CREATE INDEX idx_rel_child
ON organisation_relationships(child_entity_id);

CREATE INDEX idx_rel_type
ON organisation_relationships(relationship_type);