"""
HTTP helpers for overseas SaaS (GDrive / Notion): proxy from env + retries.
"""
from __future__ import annotations

import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 35
DEFAULT_RETRIES = 3


def get_http_proxies() -> dict | None:
    """HTTP_PROXY / HTTPS_PROXY first, then GDRIVE_PROXY_IP:PORT fallback."""
    proxies: dict = {}
    http_p = (os.getenv("HTTP_PROXY") or os.getenv("http_proxy") or "").strip()
    https_p = (os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or "").strip()
    if http_p:
        proxies["http"] = http_p
    if https_p:
        proxies["https"] = https_p
    if not proxies.get("https"):
        ip = (os.getenv("GDRIVE_PROXY_IP") or "").strip()
        port = (os.getenv("GDRIVE_PROXY_PORT") or "").strip()
        if ip and port:
            proxies["https"] = f"http://{ip}:{port}"
            if "http" not in proxies:
                proxies["http"] = proxies["https"]
    return proxies or None


def saas_request(
    method: str,
    url: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    proxies: dict | None = None,
    **kwargs,
) -> requests.Response:
    """Retry transient network errors; honor proxy env."""
    use_proxies = proxies if proxies is not None else get_http_proxies()
    last_err: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            return requests.request(
                method,
                url,
                timeout=timeout,
                proxies=use_proxies,
                **kwargs,
            )
        except Exception as e:
            last_err = e
            logger.warning(f"[SaaS-HTTP] {method} attempt {attempt + 1}/{retries} failed: {e}")
            if attempt < retries - 1:
                time.sleep(1.2 * (attempt + 1))
    raise last_err  # type: ignore[misc]
