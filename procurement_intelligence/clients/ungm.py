"""Legacy UNGM API client retained for reference only.

UNGM has confirmed that API access is restricted to UN staff. Faram's
production procurement pipeline must not use this client. Supplier-facing
ingestion is implemented in ``sources.ungm_supplier`` and accepts data that
Faram is authorized to obtain through UNGM's supplier-facing channels.

This module is intentionally retained so the earlier API design remains
traceable, but it should not be configured with UNGM API credentials.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urljoin

import requests

PRODUCTION_API = "https://www.ungm.org/API/"
TEST_API = "https://wwwtest3.ungm.org/API/"


class UNGMClient:
    """Legacy API client; unavailable for Faram supplier deployments."""

    def __init__(self, *args: Any, **kwargs: Any):
        raise RuntimeError(
            "UNGM API access is restricted to UN staff. "
            "Use procurement_intelligence.sources.ungm_supplier instead."
        )


__all__ = ["UNGMClient", "PRODUCTION_API", "TEST_API"]
