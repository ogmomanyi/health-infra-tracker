"""Shared resilient HTTP client for official procurement sources."""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_HEADERS = {
    "Accept": "application/json, application/xml, text/html;q=0.9, */*;q=0.8",
    "User-Agent": "Faram-Procurement-Intelligence/2.0 (+https://github.com/ogmomanyi/health-infra-tracker)",
}


def build_session(
    *,
    retries: int = 4,
    backoff_factor: float = 0.75,
) -> requests.Session:
    """Return a session with bounded retries for transient source failures."""
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=backoff_factor,
        status_forcelist=(408, 425, 429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=16)
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
