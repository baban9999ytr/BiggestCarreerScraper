import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.core.metadata_store import metadata_store
from config import ACTIVE_LOGIN_STATES, SESSION_TTL_SECONDS, SESSIONS

logger = logging.getLogger("kariyer_api.dependencies")


def parse_expires_at(s: dict) -> datetime:
    raw = s.get("expires_at")
    if not raw:
        return datetime.now(timezone.utc) + timedelta(seconds=SESSION_TTL_SECONDS)
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc) + timedelta(seconds=SESSION_TTL_SECONDS)


def refresh_session_ttl(s: dict):
    s["expires_at"] = (
        datetime.now(timezone.utc) + timedelta(seconds=SESSION_TTL_SECONDS)
    ).isoformat()


async def require_session(token: str, *, refresh: bool = True) -> dict:
    s = SESSIONS.get(token)
    if not s:
        # Fallback to persistent metadata store
        meta = await metadata_store.get_session(token)
        if not meta:
            raise HTTPException(404, "Geçersiz veya süresi dolmuş token.")
        s = meta
        SESSIONS[token] = s  # Cache metadata in memory

    if s.get("status") in ACTIVE_LOGIN_STATES or s.get("status") in (
        "success",
        "initiating",
        "authenticated",
    ):
        if refresh:
            refresh_session_ttl(s)
            await metadata_store.save_session(token, s)
        return s

    if datetime.now(timezone.utc) > parse_expires_at(s):
        SESSIONS.pop(token, None)
        await metadata_store.delete_session(token)
        raise HTTPException(404, "Geçersiz veya süresi dolmuş token.")

    if refresh:
        refresh_session_ttl(s)
        await metadata_store.save_session(token, s)
    return s
