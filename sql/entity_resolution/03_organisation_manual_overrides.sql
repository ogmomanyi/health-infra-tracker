DROP TABLE IF EXISTS organisation_manual_overrides;

CREATE TABLE organisation_manual_overrides (

    override_id TEXT PRIMARY KEY,

    organisation_key TEXT,

    org_ref TEXT,

    alias_name TEXT NOT NULL,

    entity_id TEXT NOT NULL,

    override_reason TEXT,

    overridden_by TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (entity_id)
        REFERENCES organisation_entities(entity_id)
);

CREATE INDEX idx_override_alias
ON organisation_manual_overrides(alias_name);

CREATE INDEX idx_override_entity
ON organisation_manual_overrides(entity_id);