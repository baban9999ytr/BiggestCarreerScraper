"""
app/core/proxy.py — On-demand outbound proxy configuration.

Reads OUTBOUND_PROXY from AppSettings and returns structured kwargs
suitable for Playwright browser.new_context() and aiohttp/httpx clients.

When OUTBOUND_PROXY is unset (the default), all helpers return None and
the callers should pass no proxy configuration at all — the runtime
behaves identically to a no-proxy environment.

Usage (Playwright):
    from app.core.proxy import get_playwright_proxy
    proxy_cfg = get_playwright_proxy()
    ctx = await browser.new_context(**({"proxy": proxy_cfg} if proxy_cfg else {}))

Usage (aiohttp):
    from app.core.proxy import get_aiohttp_proxy
    session = aiohttp.ClientSession()
    resp = await session.get(url, proxy=get_aiohttp_proxy())

Usage (httpx):
    from app.core.proxy import get_httpx_proxies
    client = httpx.AsyncClient(proxies=get_httpx_proxies())
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("kariyer_api.proxy")


def get_playwright_proxy() -> Optional[dict]:
    """
    Returns a Playwright proxy dict if OUTBOUND_PROXY is configured, else None.

    The returned dict follows Playwright's ProxySettings schema:
        {"server": "http://host:port"}
    or with credentials:
        {"server": "http://host:port", "username": "...", "password": "..."}

    Credentials embedded in the URL (http://user:pass@host:port) are returned
    as-is in the server field — Playwright accepts that format directly.
    """
    from app.core.config import settings  

    proxy_url = settings.outbound_proxy
    if not proxy_url:
        return None

    logger.info("[proxy] Outbound proxy active: %s", _redact(proxy_url))
    return {"server": proxy_url}


def get_aiohttp_proxy() -> Optional[str]:
    """
    Returns the raw proxy URL string for aiohttp.ClientSession request calls,
    or None when no proxy is configured.

    Usage:
        resp = await session.get(url, proxy=get_aiohttp_proxy())
    """
    from app.core.config import settings

    return settings.outbound_proxy or None


def get_httpx_proxies() -> Optional[dict[str, str]]:
    """
    Returns an httpx-compatible proxy mapping dict or None.

    Usage:
        client = httpx.AsyncClient(proxies=get_httpx_proxies())
    """
    from app.core.config import settings

    proxy_url = settings.outbound_proxy
    if not proxy_url:
        return None
    return {"http://": proxy_url, "https://": proxy_url}


def _redact(url: str) -> str:
    try:
        from urllib.parse import urlparse, urlunparse
        p = urlparse(url)
        if p.password:
            netloc = f"{p.username}:***@{p.hostname}" + (f":{p.port}" if p.port else "")
            return urlunparse(p._replace(netloc=netloc))
    except Exception:
        pass
    return url
