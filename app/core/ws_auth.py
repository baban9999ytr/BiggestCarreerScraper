"""
app/core/ws_auth.py
───────────────────
WebSocket pre-accept authentication helper.

Validates session tokens BEFORE upgrading the WebSocket connection.
An invalid or expired token causes an immediate close at the HTTP
upgrade stage — the connection is never accepted.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import WebSocket

from config import ACTIVE_LOGIN_STATES, SESSIONS
from app.core.metadata_store import metadata_store

logger = logging.getLogger("kariyer.ws_auth")

_WS_CLOSE_UNAUTHORIZED = 4401
_WS_CLOSE_NOT_FOUND = 4404


async def ws_require_session(ws: WebSocket, token: str) -> dict | None:
    """
    Validate a session token before upgrading a WebSocket connection.

    Must be called BEFORE ``await ws.accept()``. FastAPI/Starlette allows
    calling ``ws.close()`` prior to ``ws.accept()`` — doing so causes the
    HTTP upgrade handshake to be rejected immediately with a 403 response,
    so the caller never establishes a connection.

    Args:
        ws:    The incoming WebSocket connection (not yet accepted).
        token: The session token from the URL path.

    Returns:
        The session dict on success, or None if validation failed.
        When None is returned the connection has already been closed;
        the endpoint should simply ``return``.

    Example usage in an endpoint::

        @router.websocket("/ws/livestream/{token}")
        async def livestream(ws: WebSocket, token: str):
            session = await ws_require_session(ws, token)
            if session is None:
                return
            await ws.accept()
            ...
    """
    session = SESSIONS.get(token)
    if not session:
        meta = await metadata_store.get_session(token)
        if not meta:
            await ws.close(code=_WS_CLOSE_NOT_FOUND)
            logger.warning("WS rejected: token not found (value redacted)")
            return None
        session = meta
        SESSIONS[token] = session

    raw_exp = session.get("expires_at")
    if raw_exp:
        try:
            exp = datetime.fromisoformat(str(raw_exp).replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > exp:
                SESSIONS.pop(token, None)
                await metadata_store.delete_session(token)
                await ws.close(code=_WS_CLOSE_UNAUTHORIZED)
                logger.warning("WS rejected: session expired (token redacted)")
                return None
        except (ValueError, TypeError):
            await ws.close(code=_WS_CLOSE_UNAUTHORIZED)
            logger.warning("WS rejected: malformed expires_at field (token redacted)")
            return None

    valid_statuses: frozenset[str] = frozenset(ACTIVE_LOGIN_STATES) | {"success", "authenticated"}
    status_val = session.get("status", "")
    if status_val not in valid_statuses:
        await ws.close(code=_WS_CLOSE_UNAUTHORIZED)
        logger.warning(
            "WS rejected: session in non-streamable state '%s' (token redacted)",
            status_val,
        )
        return None

    return session
