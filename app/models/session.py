from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings
from config import SESSIONS


def public(s: dict[str, Any]) -> dict[str, Any]:
    return {
        k: s.get(k)
        for k in (
            "token",
            "status",
            "error",
            "debug_artifacts",
            "last_url",
            "created_at",
            "expires_at",
            "jobs_exported",
            "screen",
            "2fa_card",
        )
    }


def new_session(email: str) -> tuple[str, dict[str, Any]]:
    token = uuid.uuid4().hex
    s = {
        "token": token,
        "email": email,
        "status": "initiating",
        "error": None,
        "debug_artifacts": {},
        "last_url": None,
        "screen": None,
        "2fa_card": None,
        "2fa_method": None,
        "2fa_code": None,
        "2fa_resend": False,
        "page": None,
        "context": None,
        "browser": None,
        "playwright": None,
        "jobs_exported": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=settings.session_ttl_seconds)).isoformat(),
        "lock": asyncio.Lock(),
    }
    SESSIONS[token] = s
    return token, s
