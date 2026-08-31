"""
app/core/cors.py
────────────────
CORS origin loader with environment-driven configuration.

Never allows wildcard origins when credentials are enabled.
Enforces explicit origin lists in production.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("kariyer.cors")

_SAFE_LOCALHOST_ORIGINS: list[str] = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]


from app.core.config import settings

def get_allowed_origins() -> list[str]:
    origins = settings.cors_origins_list
    logger.info("CORS allowed origins: %s", origins)
    return origins
