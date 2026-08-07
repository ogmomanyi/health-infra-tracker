"""
Utilities for normalising organisation names before matching.

The functions in this module perform deterministic text
normalisation only. Higher-level semantic and alias resolution
is handled elsewhere in the entity resolution pipeline.
"""

from __future__ import annotations

import re
import unicodedata


_WHITESPACE_RE = re.compile(r"\s+")
_PUNCTUATION_RE = re.compile(r"[^\w\s]")


def normalize_name(name: str) -> str:
    """
    Convert an organisation name into a canonical comparison form.

    Steps:
    1. Remove accents/diacritics.
    2. Convert to lowercase.
    3. Remove punctuation.
    4. Collapse repeated whitespace.
    5. Trim leading/trailing whitespace.

    Parameters
    ----------
    name : str
        Raw organisation name.

    Returns
    -------
    str
        Normalised organisation name.
    """
    if not name:
        return ""

    # Remove accents
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")

    # Lowercase
    name = name.lower()

    # Remove punctuation
    name = _PUNCTUATION_RE.sub(" ", name)

    # Collapse whitespace
    name = _WHITESPACE_RE.sub(" ", name)

    return name.strip()