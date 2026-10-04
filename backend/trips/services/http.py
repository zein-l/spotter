"""Shared HTTP session for the free upstream services (OSRM, Photon, OpenRouteService)."""

from __future__ import annotations

import logging
import threading
from typing import Any

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)
_local = threading.local()


class UpstreamError(Exception):
    """A third-party service was unreachable or returned something unusable."""


def _session() -> requests.Session:
    session = getattr(_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers["User-Agent"] = settings.HTTP_USER_AGENT
        retry = Retry(
            total=2,
            connect=2,
            read=1,
            backoff_factor=0.4,
            status_forcelist=(429, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST"}),
            raise_on_status=False,
        )
        session.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=8))
        _local.session = session
    return session


def request_json(
    method: str,
    url: str,
    *,
    params: dict | None = None,
    json: Any = None,
    headers: dict | None = None,
    timeout: tuple[float, float] | float | None = None,
) -> tuple[int, Any]:
    """Return (status, parsed JSON). 4xx bodies are returned for the caller to interpret."""
    try:
        response = _session().request(
            method,
            url,
            params=params,
            json=json,
            headers=headers,
            timeout=timeout or settings.HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("Upstream request failed: %s %s (%s)", method, url, exc)
        raise UpstreamError(f"Could not reach {url.split('/')[2]}") from exc
    if response.status_code >= 500 or response.status_code == 429:
        logger.warning("Upstream error %s from %s", response.status_code, url)
        raise UpstreamError(f"{url.split('/')[2]} returned HTTP {response.status_code}")
    try:
        return response.status_code, response.json()
    except ValueError as exc:
        raise UpstreamError(f"{url.split('/')[2]} returned invalid JSON") from exc
