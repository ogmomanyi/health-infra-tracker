-- =====================================================
-- Organisation Alias Uniqueness
-- Prevent duplicate alias mappings
-- =====================================================

CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_org_alias
ON organisation_aliases(
    alias_name,
    entity_id,
    source_system
);