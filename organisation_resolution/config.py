"""
Configuration for the Organisation Entity Resolution engine.

This module centralises all configurable paths, table names,
and constants used throughout the entity resolution pipeline.
"""

from pathlib import Path

# ---------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"

DATABASE_PATH = DATA_DIR / "iati_intelligence.db"

# ---------------------------------------------------------------------
# Source tables
# ---------------------------------------------------------------------

SOURCE_ORGANISATION_TABLE = "organisation_intelligence"

# ---------------------------------------------------------------------
# Entity Resolution tables
# ---------------------------------------------------------------------

ENTITY_TABLE = "organisation_entities"

ALIAS_TABLE = "organisation_aliases"

RELATIONSHIP_TABLE = "organisation_relationships"

RESOLUTION_LOG_TABLE = "organisation_resolution_log"

MANUAL_OVERRIDE_TABLE = "organisation_manual_overrides"

# ---------------------------------------------------------------------
# Matching configuration
# ---------------------------------------------------------------------

DEFAULT_MATCH_CONFIDENCE = 1.0

MIN_FUZZY_CONFIDENCE = 0.90

NORMALIZE_CASE = True

REMOVE_PUNCTUATION = True

COLLAPSE_WHITESPACE = True