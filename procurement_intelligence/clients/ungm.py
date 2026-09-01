"""UNGM Notice API client with runtime-only OAuth credentials.

The client supports both a supplied access token and the OAuth 2.0 client
credential flow. Secrets are read only from the local environment and are never
persisted by this module.
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
        client_id: str | None = None,
        client_secret: str | None = None,
        base_url: str = PRODUCTION_API,
        timeout: int = 30,
    ):
        self.access_token = access_token or os.getenv("UNGM_ACCESS_TOKEN", "")
        self.client_id = client_id or os.getenv("UNGM_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("UNGM_CLIENT_SECRET", "")
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout

    def _token_url(self) -> str:
        return urljoin(self.base_url, "token")

    def _obtain_client_token(self) -> str:
        if not self.client_id or not self.client_secret:
            raise RuntimeError(
                "UNGM credentials are not set. Set UNGM_ACCESS_TOKEN, or set "
                "UNGM_CLIENT_ID and UNGM_CLIENT_SECRET locally."
            )

        response = requests.post(
            self._token_url(),
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise ValueError("UNGM token response did not contain access_token")
        return token

    def _headers(self) -> dict[str, str]:
        if not self.access_token:
            self.access_token = self._obtain_client_token()
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
