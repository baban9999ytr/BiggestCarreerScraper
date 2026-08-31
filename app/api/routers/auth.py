import asyncio
import json
import logging
import os
from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket
from fastapi.responses import StreamingResponse

from app.core.config import settings
from config import ACTIVE_LOGIN_STATES, SESSIONS, args
from app.models.schemas import LoginCredentials, TokenOnly, TwoFactorChoice, TwoFactorSubmission
from app.models.session import new_session, public
from app.api.dependencies import require_session
from app.core.ws_auth import ws_require_session
from automation import handle_login_and_verification

logger = logging.getLogger("kariyer_api.auth")
router = APIRouter()

async def capture_2fa_post_submission_screenshots(token: str, duration_seconds: int = 60) -> None:
    session = SESSIONS.get(token)
    if not session:
        return

    logger.info("Starting post-2FA screenshot capture worker for token: %s", token)
    for step in range(1, duration_seconds + 1):
        if token not in SESSIONS or session.get("status") == "closed":
            break

        page = session.get("page")
        if page and not page.is_closed():
            try:
                filename = f"2fa-postcode-{token}-{step:02d}s.jpg"
                filepath = os.path.join(str(settings.debug_dir), filename)

                async with session["lock"]:
                    await page.screenshot(path=filepath, type="jpeg", quality=60)

                logger.info("Captured post-2FA screenshot (%d/%ds): %s", step, duration_seconds, filename)
            except Exception as e:
                logger.debug("Failed to take post-2FA screenshot tick %d: %s", step, e)

        await asyncio.sleep(1)

    logger.info("Completed post-2FA screenshot capture worker for token: %s", token)


@router.post("/login")
async def login(c: LoginCredentials, tasks: BackgroundTasks):
    token, s = new_session(c.email)
    tasks.add_task(handle_login_and_verification, token, c.email, c.password, True, getattr(args, "testerhtml", False))    
    return {
        "status": s["status"],
        "token": token,
        "status_url": f"/session-status/{token}",
        "livestream_url": f"/ws/livestream/{token}",
        "verification_url": f"/?token={token}",
    }


@router.get("/session-status/{token}")
async def status(token: str):
    s = await require_session(token)
    page = s.get("page")

    if page and not page.is_closed() and s.get("status") in ACTIVE_LOGIN_STATES:
        try:
            url = page.url.lower()
            if "ats.kariyer.net" in url and "login" not in url:
                if (await page.locator("#user-info, #dashboard-job-list, .wide-card.job-card").count()) > 0:
                    s["status"] = "success"
                    s["screen"] = "authenticated"
        except Exception:
            pass

    return public(s)


@router.get("/stream-status/{token}")
async def stream_status(token: str):
    await require_session(token)

    async def events():
        previous = None
        last_ping = 0.0
        while token in SESSIONS:
            try:
                s = await require_session(token)
            except HTTPException:
                yield 'data: {"status":"expired"}\n\n'
                return
            v = json.dumps(public(s))
            now = asyncio.get_running_loop().time()
            if v != previous:
                previous = v
                yield f"data: {v}\n\n"
                last_ping = now
            elif now - last_ping >= 5:
                yield ": keepalive\n\n"
                last_ping = now
            if s["status"] == "closed":
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/submit-2fa-choice")
async def choose(p: TwoFactorChoice):
    s = await require_session(p.token)
    if s["status"] not in ACTIVE_LOGIN_STATES:
        raise HTTPException(
            400,
            f"Session is in terminal state '{s['status']}' and cannot accept a 2FA choice."
            + (f" Error: {s['error']}" if s.get("error") else ""),
        )
    if p.method not in ("email", "sms"):
        raise HTTPException(400, "Invalid 2FA method. Must be 'email' or 'sms'.")
    s["2fa_method"] = p.method
    s["error"] = None
    logger.info("2FA method accepted via API: %s (state was '%s', screen=%s, card=%s)", p.method, s["status"], s.get("screen"), s.get("2fa_card"))
    return {
        "status": "accepted",
        "current_state": s["status"],
        "screen": s.get("screen"),
        "2fa_card": s.get("2fa_card"),
        "method": p.method,
    }


@router.post("/submit-2fa-code")
async def code(p: TwoFactorSubmission, tasks: BackgroundTasks):
    s = await require_session(p.token)
    if s["status"] not in ACTIVE_LOGIN_STATES:
        raise HTTPException(
            400,
            f"Session is in terminal state '{s['status']}' and cannot accept a 2FA code."
            + (f" Error: {s['error']}" if s.get("error") else ""),
        )
    s["2fa_code"] = p.code
    s["error"] = None
    logger.info("2FA code accepted via API (state was '%s', screen=%s, card=%s)", s["status"], s.get("screen"), s.get("2fa_card"))
    tasks.add_task(capture_2fa_post_submission_screenshots, p.token, 60)
    return {
        "status": "accepted",
        "current_state": s["status"],
        "screen": s.get("screen"),
        "2fa_card": s.get("2fa_card"),
    }


@router.post("/resend-2fa-code")
async def resend_2fa(p: TokenOnly):
    s = await require_session(p.token)
    if s["status"] not in ACTIVE_LOGIN_STATES:
        raise HTTPException(400, f"Session is in terminal state '{s['status']}' and cannot resend 2FA.")
    s["2fa_resend"] = True
    s["2fa_code"] = None
    s["error"] = None
    logger.info("2FA resend requested (state was '%s', card=%s)", s["status"], s.get("2fa_card"))
    return {"status": "accepted", "current_state": s["status"]}


@router.post("/close-session")
async def close_session(p: TokenOnly):
    s = await require_session(p.token, refresh=False)
    s["status"] = "closed"
    logger.info("Session close requested for %s", p.token)
    return {"status": "closed"}


@router.websocket("/ws/livestream/{token}")
async def livestream(ws: WebSocket, token: str):
    s = await ws_require_session(ws, token)
    if s is None:
        return  # already closed by ws_require_session

    await ws.accept()

    page = s.get("page")
    for _ in range(300):
        page = s.get("page")
        if page is not None:
            try:
                if not page.is_closed():
                    break
            except Exception:
                pass
        await asyncio.sleep(0.1)
    else:
        await ws.close(code=4404)
        return

    try:
        while token in SESSIONS and not page.is_closed():
            try:
                m = await asyncio.wait_for(ws.receive_json(), 0.1)
                action = m.get("action")
                x = m.get("x")
                y = m.get("y")

                if action in ("click", "mousedown", "mousemove", "mouseup"):
                    if not (isinstance(x, (int, float)) and isinstance(y, (int, float))):
                        continue  # drop malformed coordinate messages
                    x = max(0.0, min(float(x), 4096.0))
                    y = max(0.0, min(float(y), 4096.0))
                    async with s["lock"]:
                        if action == "click":
                            await page.mouse.click(x, y)
                        elif action == "mousedown":
                            await page.mouse.move(x, y)
                        elif action == "mousemove":
                            await page.mouse.move(x, y)
                        elif action == "mouseup":
                            await page.mouse.up()
            except asyncio.TimeoutError:
                pass

            if token not in SESSIONS or s["status"] == "closed":
                break

            try:
                async with s["lock"]:
                    buf = await page.screenshot(type="jpeg", quality=40)
                await ws.send_bytes(buf)
            except Exception:
                pass

            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("WS stream error for %s: %s", token, e)
    finally:
        try:
            await ws.close()
        except Exception:
            pass
