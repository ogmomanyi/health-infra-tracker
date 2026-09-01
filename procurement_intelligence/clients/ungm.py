"""Authenticated UNGM Notice API client.

Credentials and access tokens are supplied at runtime. Nothing secret is stored
in the repository. The client follows UNGM's OData pagination using the
``@odata.nextLink`` returned by the API.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urljoin

import requests

PRODUCTION_API = "https://www.ungm.org/API/"
TEST_API = "https://wwwtest3.ungm.org/API/"


class UNGMClient:
    def __init__(
        self,
        access_token: str | None = None,
        base_url: str = PRODUCTION_API,
        timeout: int = 30,
    ):
        self.access_token = access_token or os.getenv("UNGM_ACCESS_TOKEN", "")
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        if not self.access_token:
            raise RuntimeError(
                "UNGM_ACCESS_TOKEN is not set. Obtain an OAuth access token and "
                "set it in the local environment before calling the Notice API."
            )
        return {
            "Accept": "application/json",
            "Authorization": f"bearer {self.access_token}",
        }

    def get_notices(self, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Fetch all notice pages, following OData ``@odata.nextLink``."""
        url = urljoin(self.base_url, "Notices")
        records: list[dict[str, Any]] = []
        session = requests.Session()

        while url:
            response = session.get(
                url,
                headers=self._headers(),
                params=params if url.endswith("/Notices") else None,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            page = payload.get("value", payload if isinstance(payload, list) else [])
            if not isinstance(page, list):
                raise ValueError("Unexpected UNGM Notices response: 'value' is not a list")
            records.extend(page)
            url = payload.get("@odata.nextLink") if isinstance(payload, dict) else None
            params = None

        return records


__all__ = ["UNGMClient", "PRODUCTION_API", "TEST_API"]
