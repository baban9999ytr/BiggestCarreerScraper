# from __future__ import annotations

# import argparse
# import asyncio
# import csv
# import json
# import logging
# from automation_extract_candidate_details import process_candidate_details_for_token
# import automation_extract_candidate_details
# import os
# import sys
# import uuid
# from contextlib import asynccontextmanager
# from datetime import datetime, timedelta, timezone
# from typing import Any, Optional

# import uvicorn
# from dotenv import load_dotenv
# from fastapi import (
#     APIRouter,
#     BackgroundTasks,
#     FastAPI,
#     HTTPException,
#     WebSocket,
#     WebSocketDisconnect,
# )
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import FileResponse, StreamingResponse
# from pydantic import BaseModel, Field

# from schemas import ExportRequest
# from automation import handle_login_and_verification
# from automation_process_jobs import extract_and_send_jobs, process_jobs_task
# from config import (
#     ACTIVE_LOGIN_STATES,
#     EXPORT_DIR,
#     SCREENSHOT_DIR,
#     SESSION_TTL_SECONDS,
#     SESSIONS,
#     logger,
# )
# from models import (
#     ExportRequest,
#     LoginCredentials,
#     TokenOnly,
#     TwoFactorChoice,
#     TwoFactorSubmission,
#     new_session,
#     public,
# )

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger("main")

# load_dotenv()
# ENV_EMAIL = os.getenv("KARIYER_EMAIL")
# ENV_PASSWORD = os.getenv("KARIYER_PASSWORD")
# DEBUG_DIR = os.getenv("DEBUG_DIR", "./debug")

# os.makedirs(DEBUG_DIR, exist_ok=True)

# GEEKED_PATH = os.path.join(os.path.expanduser("~"), "Desktop", "LastRodeo", "GeekedTest")
# if os.path.exists(GEEKED_PATH):
#     sys.path.append(GEEKED_PATH)

# try:
#     from geeked import Geeked
# except ImportError as e:
#     Geeked = None
#     logger.warning("GeekedTest module not found. Auto-captcha disabled: %s", e)

# parser = argparse.ArgumentParser(description="FastAPI Web Service with Playwright Verification")
# parser.add_argument("--autosolvetester", action="store_true", help="Run in auto-solve test mode")
# parser.add_argument("--testerhtml", action="store_true", help="Dump DOM HTML of active pages every 10 seconds")
# args, _ = parser.parse_known_args()


# def refresh_session_ttl(s: dict) -> None:
#     s["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=SESSION_TTL_SECONDS)).isoformat()


# def parse_expires_at(s: dict) -> datetime:
#     raw = s.get("expires_at")
#     if not raw:
#         return datetime.now(timezone.utc) + timedelta(seconds=SESSION_TTL_SECONDS)
#     try:
#         return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
#     except Exception:
#         return datetime.now(timezone.utc) + timedelta(seconds=SESSION_TTL_SECONDS)


# def require_session(token: str, *, refresh: bool = True) -> dict:
#     s = SESSIONS.get(token)
#     if not s:
#         raise HTTPException(404, "Geçersiz veya süresi dolmuş token.")
#     if s.get("status") in ACTIVE_LOGIN_STATES or s.get("status") in ("success", "initiating", "authenticated"):
#         if refresh:
#             refresh_session_ttl(s)
#         return s
#     if datetime.now(timezone.utc) > parse_expires_at(s):
#         SESSIONS.pop(token, None)
#         raise HTTPException(404, "Geçersiz veya süresi dolmuş token.")
#     if refresh:
#         refresh_session_ttl(s)
#     return s


# def write_exports(token: str, jobs: list[dict]) -> dict[str, str]:
#     stem = f"kariyer_jobs_{token}_{uuid.uuid4().hex[:8]}"
#     j, c = f"{stem}.json", f"{stem}.csv"
#     with open(os.path.join(EXPORT_DIR, j), "w", encoding="utf-8") as f:
#         json.dump(jobs, f, ensure_ascii=False, indent=2)

#     cols = ["title", "reference_number", "company", "applications_count", "pozisyon", "ilan_basligi", "candidates"]
#     with open(os.path.join(EXPORT_DIR, c), "w", encoding="utf-8-sig", newline="") as f:
#         w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
#         w.writeheader()
#         for x in jobs:
#             w.writerow({
#                 k: json.dumps(x[k], ensure_ascii=False) if isinstance(x.get(k), (list, dict)) else x.get(k, "") 
#                 for k in cols
#             })
#     return {"json": f"/exports/{j}", "csv": f"/exports/{c}"}


# async def start_html_dumper(token: str, interval: int = 10) -> None:
#     """Periodically dumps the current DOM tree of active Playwright pages to disk."""
#     session = SESSIONS.get(token)
#     if not session:
#         return

#     logger.info("Started HTML dumper worker for token: %s (interval: %ds)", token, interval)
#     counter = 1

#     while token in SESSIONS and session.get("status") not in ("closed", "failed"):
#         page = session.get("page")
#         if page and not page.is_closed():
#             try:
#                 async with session["lock"]:
#                     html_content = await page.content()
                
#                 filename = f"dom-{token}-{counter:03d}.html"
#                 filepath = os.path.join(DEBUG_DIR, filename)

#                 with open(filepath, "w", encoding="utf-8") as f:
#                     f.write(html_content)

#                 logger.info("HTML dumper saved DOM state: %s", filename)
#                 counter += 1
#             except Exception as e:
#                 logger.debug("HTML dumper tick failed for token %s: %s", token, e)

#         await asyncio.sleep(interval)
#     logger.info("HTML dumper worker stopped for token: %s", token)


# router = APIRouter(tags=["Enterprise Automation API"])

# @router.post("/process-candidate-details")
# async def process_candidate_details(p: TokenOnly, tasks: BackgroundTasks):
#     s = require_session(p.token)
#     page = s.get("page") if s else None

#     if not page or s.get("status") not in ("success", "authenticated"):
#         raise HTTPException(400, "Session is not ready or authenticated.")

#     if s.get("is_processing_candidate_details"):
#         raise HTTPException(409, "A candidate details extraction task is already running for this session.")

#     s["is_processing_candidate_details"] = True

#     async def _candidate_runner():
#         try:
#             async with s["lock"]:
#                 out_path = await process_candidate_details_for_token(
#                     token=p.token,
#                     page=page,
#                     search_dir=EXPORT_DIR,
#                     output_dir=EXPORT_DIR
#                 )

#             if out_path:
#                 s["candidate_details_file"] = f"/exports/{out_path.name}"
#                 s["last_candidate_export_result"] = {
#                     "status": "completed",
#                     "export_url": f"/exports/{out_path.name}"
#                 }
#             else:
#                 s["last_candidate_export_result"] = {
#                     "status": "failed",
#                     "error": "No job listings JSON found for this token."
#                 }
#         except Exception as e:
#             logger.exception("Background candidate details processing failed for token %s: %s", p.token, e)
#             s["last_candidate_export_result"] = {"status": "failed", "error": str(e)}
#         finally:
#             s["is_processing_candidate_details"] = False

#     tasks.add_task(_candidate_runner)

#     return {
#         "status": "processing",
#         "token": p.token,
#         "message": "Candidate CV details extraction started in background."
#     }


# @router.get("/candidate-details-status/{token}")
# async def candidate_details_status(token: str):
#     s = require_session(token)
#     return {
#         "token": token,
#         "is_processing": s.get("is_processing_candidate_details", False),
#         "result": s.get("last_candidate_export_result")
#     }
    
# @router.get("/index", response_class=FileResponse)
# async def index():
#     return FileResponse("index.html")


# @router.post("/login")
# async def login(c: LoginCredentials, tasks: BackgroundTasks):
#     token, s = new_session(c.email)
#     tasks.add_task(handle_login_and_verification, token, c.email, c.password)
    
#     # HTML dumper bayrağı aktifse ve dumper henüz başlamadıysa tetikle
#     if args.testerhtml and not s.get("html_dumper_started"):
#         s["html_dumper_started"] = True
#         tasks.add_task(start_html_dumper, token, 10)

#     return {
#         "status": s["status"],
#         "token": token,
#         "status_url": f"/session-status/{token}",
#         "livestream_url": f"/ws/livestream/{token}",
#         "verification_url": f"/?token={token}",
#     }


# @router.get("/session-status/{token}")
# async def status(token: str, tasks: BackgroundTasks):
#     s = require_session(token)
#     page = s.get("page")

#     # Sayfa nesnesi oluştuktan hemen sonra HTML dumper'ı otomatik başlatır
#     if args.testerhtml and page and not s.get("html_dumper_started"):
#         s["html_dumper_started"] = True
#         tasks.add_task(start_html_dumper, token, 10)

#     if page and not page.is_closed() and s.get("status") in ACTIVE_LOGIN_STATES:
#         try:
#             url = page.url.lower()
#             if "ats.kariyer.net" in url and "login" not in url:
#                 if (await page.locator("#user-info, #dashboard-job-list, .wide-card.job-card").count()) > 0:
#                     s["status"] = "success"
#                     s["screen"] = "authenticated"
#         except Exception:
#             pass

#     return public(s)


# @router.get("/stream-status/{token}")
# async def stream_status(token: str):
#     require_session(token)

#     async def events():
#         previous = None
#         last_ping = 0.0
#         while token in SESSIONS:
#             try:
#                 s = require_session(token)
#             except HTTPException:
#                 yield 'data: {"status":"expired"}\n\n'
#                 return
#             v = json.dumps(public(s))
#             now = asyncio.get_running_loop().time()
#             if v != previous:
#                 previous = v
#                 yield f"data: {v}\n\n"
#                 last_ping = now
#             elif now - last_ping >= 5:
#                 yield ": keepalive\n\n"
#                 last_ping = now
#             if s["status"] == "closed":
#                 return
#             await asyncio.sleep(0.5)

#     return StreamingResponse(events(), media_type="text/event-stream")


# @router.post("/submit-2fa-choice")
# async def choose(p: TwoFactorChoice):
#     s = require_session(p.token)
#     if s["status"] not in ACTIVE_LOGIN_STATES:
#         raise HTTPException(
#             400,
#             f"Session is in terminal state '{s['status']}' and cannot accept a 2FA choice."
#             + (f" Error: {s['error']}" if s.get("error") else ""),
#         )
#     if p.method not in ("email", "sms"):
#         raise HTTPException(400, "Invalid 2FA method. Must be 'email' or 'sms'.")
#     s["2fa_method"] = p.method
#     s["error"] = None
#     logger.info("2FA method accepted via API: %s (state was '%s', screen=%s, card=%s)", p.method, s["status"], s.get("screen"), s.get("2fa_card"))
#     return {
#         "status": "accepted",
#         "current_state": s["status"],
#         "screen": s.get("screen"),
#         "2fa_card": s.get("2fa_card"),
#         "method": p.method,
#     }


# @router.post("/submit-2fa-code")
# async def code(p: TwoFactorSubmission, tasks: BackgroundTasks):
#     s = require_session(p.token)
#     if s["status"] not in ACTIVE_LOGIN_STATES:
#         raise HTTPException(
#             400,
#             f"Session is in terminal state '{s['status']}' and cannot accept a 2FA code."
#             + (f" Error: {s['error']}" if s.get("error") else ""),
#         )
#     s["2fa_code"] = p.code
#     s["error"] = None
#     logger.info("2FA code accepted via API (state was '%s', screen=%s, card=%s)", s["status"], s.get("screen"), s.get("2fa_card"))
#     tasks.add_task(capture_2fa_post_submission_screenshots, p.token, 60)
#     return {
#         "status": "accepted",
#         "current_state": s["status"],
#         "screen": s.get("screen"),
#         "2fa_card": s.get("2fa_card"),
#     }


# @router.post("/resend-2fa-code")
# async def resend_2fa(p: TokenOnly):
#     s = require_session(p.token)
#     if s["status"] not in ACTIVE_LOGIN_STATES:
#         raise HTTPException(400, f"Session is in terminal state '{s['status']}' and cannot resend 2FA.")
#     s["2fa_resend"] = True
#     s["2fa_code"] = None
#     s["error"] = None
#     logger.info("2FA resend requested (state was '%s', card=%s)", s["status"], s.get("2fa_card"))
#     return {"status": "accepted", "current_state": s["status"]}


# @router.post("/close-session")
# async def close_session(p: TokenOnly):
#     s = require_session(p.token, refresh=False)
#     s["status"] = "closed"
#     logger.info("Session close requested for %s", p.token)
#     return {"status": "closed"}


# @router.websocket("/ws/livestream/{token}")
# async def livestream(ws: WebSocket, token: str):
#     try:
#         s = require_session(token)
#     except HTTPException:
#         await ws.accept()
#         await ws.close(code=4404)
#         return
#     await ws.accept()
#     page = s.get("page")
#     for _ in range(300):
#         page = s.get("page")
#         if page is not None:
#             try:
#                 if not page.is_closed():
#                     break
#             except Exception:
#                 pass
#         await asyncio.sleep(0.1)
#     else:
#         await ws.close(code=4404)
#         return

#     try:
#         while token in SESSIONS and not page.is_closed():
#             try:
#                 m = await asyncio.wait_for(ws.receive_json(), 0.1)
#                 if m.get("action") == "click" and isinstance(m.get("x"), (int, float)) and isinstance(m.get("y"), (int, float)):
#                     async with s["lock"]:
#                         await page.mouse.click(m["x"], m["y"])
#                 elif m.get("action") == "mousedown" and isinstance(m.get("x"), (int, float)) and isinstance(m.get("y"), (int, float)):
#                     async with s["lock"]:
#                         await page.mouse.move(m["x"], m["y"])
#                         await page.mouse.down()
#                 elif m.get("action") == "mousemove" and isinstance(m.get("x"), (int, float)) and isinstance(m.get("y"), (int, float)):
#                     async with s["lock"]:
#                         await page.mouse.move(m["x"], m["y"])
#                 elif m.get("action") == "mouseup" and isinstance(m.get("x"), (int, float)) and isinstance(m.get("y"), (int, float)):
#                     async with s["lock"]:
#                         await page.mouse.move(m["x"], m["y"])
#                         await page.mouse.up()
#                 elif m.get("action") == "close":
#                     break
#             except asyncio.TimeoutError:
#                 pass

#             try:
#                 async with s["lock"]:
#                     frame = await page.screenshot(type="jpeg", quality=50)
#                 await ws.send_bytes(frame)
#             except Exception:
#                 break
#     except WebSocketDisconnect:
#         pass
#     except Exception:
#         logger.exception("Livestream failed")


# @router.post("/process-jobs")
# async def process_jobs(p: ExportRequest, tasks: BackgroundTasks):
#     s = require_session(p.token)    
#     page = s.get("page") if s else None

#     if not page or s.get("status") not in ("success", "authenticated"):
#         raise HTTPException(400, "Session is not ready or authenticated.")

#     if s.get("is_processing_jobs"):
#         raise HTTPException(409, "A job processing task is already running for this session.")

#     s["is_processing_jobs"] = True

#     async def _runner():
#         try:
#             async with s["lock"]:
#                 filter_payload = p.filters.model_dump()

#                 jobs = await process_jobs_task(
#                     page=page, 
#                     limit=p.limit,
#                     filters=filter_payload
#                 )

#             exports = write_exports(p.token, jobs)
#             s["jobs_exported"] = len(jobs)
#             s["last_export_result"] = {
#                 "status": "completed",
#                 "count": len(jobs),
#                 "exports": exports
#             }
#         except Exception as e:
#             logger.exception("Background job processing failed for token %s: %s", p.token, e)
#             s["last_export_result"] = {"status": "failed", "error": str(e)}
#         finally:
#             s["is_processing_jobs"] = False

#     tasks.add_task(_runner)

#     return {
#         "status": "processing",
#         "token": p.token,
#         "message": f"Job processing started in background for limit={p.limit}."
#     }


# @router.get("/export-status/{token}")
# async def export_status(token: str):
#     s = require_session(token)
#     return {
#         "token": token,
#         "is_processing": s.get("is_processing_jobs", False),
#         "jobs_exported": s.get("jobs_exported", 0),
#         "result": s.get("last_export_result")
#     }


# class HandleJobsRequest(BaseModel):
#     target_url: str = Field(
#         default="https://httpbin.org/post",
#         description="Destination URL to receive the extracted job and applicant payload via POST request."
#     )
#     limit: int = Field(default=10, description="Maximum number of job listings to process.")


# @asynccontextmanager
# async def lifespan(app_instance: FastAPI):
#     try:
#         from export_openapi import export_openapi_schema
#         export_openapi_schema("openapi.json")
#     except Exception as e:
#         logger.warning("OpenAPI schema export skipped or failed: %s", e)
#     yield


# app = FastAPI(
#     title="Kariyer Automation API",
#     lifespan=lifespan,
#     docs_url="/docs",
#     redoc_url="/redoc",
#     openapi_url="/openapi.json"
# )

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# app.include_router(router)


# @app.get("/")
# async def root():
#     return {"status": "online"}


# @app.get("/health")
# async def health_check():
#     return {"status": "healthy"}


# @app.post("/handle-jobs/{token}")
# async def handle_jobs_endpoint(
#     token: str, 
#     req: HandleJobsRequest, 
#     background_tasks: BackgroundTasks
# ):
#     session = SESSIONS.get(token)

#     if not session or not session.get("page"):
#         raise HTTPException(status_code=404, detail="Active session or browser page not found for this token.")

#     page = session["page"]

#     if page.is_closed():
#         raise HTTPException(status_code=400, detail="Browser page for this session is already closed.")

#     background_tasks.add_task(
#         extract_and_send_jobs,
#         page=page,
#         target_api_url=req.target_url,
#         limit=req.limit
#     )

#     return {
#         "status": "processing",
#         "message": f"Job processing started for token {token}. Extracted data will be POSTed to {req.target_url}",
#         "limit": req.limit
#     }


# async def tester():
#     if not ENV_EMAIL or not ENV_PASSWORD:
#         raise RuntimeError("KARIYER_EMAIL and KARIYER_PASSWORD environment variables are required.")

#     t, s = new_session(ENV_EMAIL)

#     async def snapshot_worker():
#         c = 1
#         while t in SESSIONS and s.get("status") not in ("success", "failed"):
#             page = s.get("page")
#             if page and not page.is_closed():
#                 try:
#                     filename = f"{t}-({c}).jpg"
#                     filepath = os.path.join(DEBUG_DIR, filename)
#                     async with s["lock"]:
#                         await page.screenshot(path=filepath, type="jpeg", quality=60)
#                     logger.info("Auto-tester took screenshot: %s", filename)
#                     c += 1
#                 except Exception as e:
#                     logger.debug("Screenshot worker tick failed: %s", e)
#             await asyncio.sleep(5)

#     login_task = asyncio.create_task(handle_login_and_verification(t, ENV_EMAIL, ENV_PASSWORD, False))

#     while not s.get("page"):
#         await asyncio.sleep(0.2)

#     snap_task = asyncio.create_task(snapshot_worker())
    
#     html_task = None
#     if args.testerhtml:
#         html_task = asyncio.create_task(start_html_dumper(t, 10))

#     await login_task
#     snap_task.cancel()
#     if html_task:
#         html_task.cancel()

#     logger.info(json.dumps(public(SESSIONS[t])))


# async def capture_2fa_post_submission_screenshots(token: str, duration_seconds: int = 60) -> None:
#     session = SESSIONS.get(token)
#     if not session:
#         return

#     logger.info("Starting post-2FA screenshot capture worker for token: %s", token)
#     for step in range(1, duration_seconds + 1):
#         if token not in SESSIONS or session.get("status") == "closed":
#             break

#         page = session.get("page")
#         if page and not page.is_closed():
#             try:
#                 filename = f"2fa-postcode-{token}-{step:02d}s.jpg"
#                 filepath = os.path.join(DEBUG_DIR, filename)

#                 async with session["lock"]:
#                     await page.screenshot(path=filepath, type="jpeg", quality=60)

#                 logger.info("Captured post-2FA screenshot (%d/%ds): %s", step, duration_seconds, filename)
#             except Exception as e:
#                 logger.debug("Failed to take post-2FA screenshot tick %d: %s", step, e)

#         await asyncio.sleep(1)

#     logger.info("Completed post-2FA screenshot capture worker for token: %s", token)

# if __name__ == "__main__":
#     if args.autosolvetester:
#         asyncio.run(tester())
#     else:
#         uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)


from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import (
    APIRouter,
    BackgroundTasks,
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from supabaser import process_and_upload
from schemas import ExportRequest
from automation import handle_login_and_verification
from automation_process_jobs import extract_and_send_jobs, process_jobs_task
from automation_extract_candidate_details import process_candidate_details_for_token
from config import (
    ACTIVE_LOGIN_STATES,
    EXPORT_DIR,
    SCREENSHOT_DIR,
    SESSION_TTL_SECONDS,
    SESSIONS,
    logger,
)
from models import (
    ExportRequest,
    LoginCredentials,
    TokenOnly,
    TwoFactorChoice,
    TwoFactorSubmission,
    new_session,
    public,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

load_dotenv()
ENV_EMAIL = os.getenv("KARIYER_EMAIL")
ENV_PASSWORD = os.getenv("KARIYER_PASSWORD")
DEBUG_DIR = os.getenv("DEBUG_DIR", "./debug")

os.makedirs(DEBUG_DIR, exist_ok=True)

GEEKED_PATH = os.path.join(os.path.expanduser("~"), "Desktop", "LastRodeo", "GeekedTest")
if os.path.exists(GEEKED_PATH):
    sys.path.append(GEEKED_PATH)

try:
    from geeked import Geeked
except ImportError as e:
    Geeked = None
    logger.warning("GeekedTest module not found. Auto-captcha disabled: %s", e)

parser = argparse.ArgumentParser(description="FastAPI Web Service with Playwright Verification")
parser.add_argument("--autosolvetester", action="store_true", help="Run in auto-solve test mode")
parser.add_argument("--testerhtml", action="store_true", help="Dump DOM HTML of active pages every 10 seconds")
args, _ = parser.parse_known_args()


def refresh_session_ttl(s: dict) -> None:
    s["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=SESSION_TTL_SECONDS)).isoformat()


def parse_expires_at(s: dict) -> datetime:
    raw = s.get("expires_at")
    if not raw:
        return datetime.now(timezone.utc) + timedelta(seconds=SESSION_TTL_SECONDS)
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc) + timedelta(seconds=SESSION_TTL_SECONDS)


def require_session(token: str, *, refresh: bool = True) -> dict:
    s = SESSIONS.get(token)
    if not s:
        raise HTTPException(404, "Geçersiz veya süresi dolmuş token.")
    if s.get("status") in ACTIVE_LOGIN_STATES or s.get("status") in ("success", "initiating", "authenticated"):
        if refresh:
            refresh_session_ttl(s)
        return s
    if datetime.now(timezone.utc) > parse_expires_at(s):
        SESSIONS.pop(token, None)
        raise HTTPException(404, "Geçersiz veya süresi dolmuş token.")
    if refresh:
        refresh_session_ttl(s)
    return s


def write_exports(token: str, jobs: list[dict]) -> dict[str, str]:
    stem = f"kariyer_jobs_{token}_{uuid.uuid4().hex[:8]}"
    j, c = f"{stem}.json", f"{stem}.csv"
    with open(os.path.join(EXPORT_DIR, j), "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)

    cols = ["title", "reference_number", "company", "applications_count", "pozisyon", "ilan_basligi", "candidates"]
    with open(os.path.join(EXPORT_DIR, c), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for x in jobs:
            w.writerow({
                k: json.dumps(x[k], ensure_ascii=False) if isinstance(x.get(k), (list, dict)) else x.get(k, "") 
                for k in cols
            })
    return {"json": f"/exports/{j}", "csv": f"/exports/{c}"}


router = APIRouter(tags=["Enterprise Automation API"])

@router.post("/process-candidate-details")
async def process_candidate_details(p: TokenOnly, tasks: BackgroundTasks):
    s = require_session(p.token)
    page = s.get("page") if s else None

    if not page or s.get("status") not in ("success", "authenticated"):
        raise HTTPException(400, "Session is not ready or authenticated.")

    if s.get("is_processing_candidate_details"):
        raise HTTPException(409, "A candidate details extraction task is already running for this session.")

    s["is_processing_candidate_details"] = True

    async def _candidate_runner():
        try:
            async with s["lock"]:
                out_path = await process_candidate_details_for_token(
                    token=p.token,
                    page=page,
                    search_dir=EXPORT_DIR,
                    output_dir=EXPORT_DIR
                )

            if out_path:
                s["candidate_details_file"] = f"/exports/{out_path.name}"
                s["last_candidate_export_result"] = {
                    "status": "completed",
                    "export_url": f"/exports/{out_path.name}"
                }
            else:
                s["last_candidate_export_result"] = {
                    "status": "failed",
                    "error": "No job listings JSON found for this token."
                }
        except Exception as e:
            logger.exception("Background candidate details processing failed for token %s: %s", p.token, e)
            s["last_candidate_export_result"] = {"status": "failed", "error": str(e)}
        finally:
            s["is_processing_candidate_details"] = False

    tasks.add_task(_candidate_runner)

    return {
        "status": "processing",
        "token": p.token,
        "message": "Candidate CV details extraction started in background."
    }


@router.get("/candidate-details-status/{token}")
async def candidate_details_status(token: str):
    s = require_session(token)
    return {
        "token": token,
        "is_processing": s.get("is_processing_candidate_details", False),
        "result": s.get("last_candidate_export_result")
    }

@router.get("/index", response_class=FileResponse)
async def index():
    return FileResponse("index.html")


@router.post("/login")
async def login(c: LoginCredentials, tasks: BackgroundTasks):
    token, s = new_session(c.email)
    tasks.add_task(handle_login_and_verification, token, c.email, c.password, True, args.testerhtml)    
    return {
        "status": s["status"],
        "token": token,
        "status_url": f"/session-status/{token}",
        "livestream_url": f"/ws/livestream/{token}",
        "verification_url": f"/?token={token}",
    }


@router.get("/session-status/{token}")
async def status(token: str):
    s = require_session(token)
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
    require_session(token)

    async def events():
        previous = None
        last_ping = 0.0
        while token in SESSIONS:
            try:
                s = require_session(token)
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
    s = require_session(p.token)
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
    s = require_session(p.token)
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
    s = require_session(p.token)
    if s["status"] not in ACTIVE_LOGIN_STATES:
        raise HTTPException(400, f"Session is in terminal state '{s['status']}' and cannot resend 2FA.")
    s["2fa_resend"] = True
    s["2fa_code"] = None
    s["error"] = None
    logger.info("2FA resend requested (state was '%s', card=%s)", s["status"], s.get("2fa_card"))
    return {"status": "accepted", "current_state": s["status"]}


@router.post("/close-session")
async def close_session(p: TokenOnly):
    s = require_session(p.token, refresh=False)
    s["status"] = "closed"
    logger.info("Session close requested for %s", p.token)
    return {"status": "closed"}


@router.websocket("/ws/livestream/{token}")
async def livestream(ws: WebSocket, token: str):
    try:
        s = require_session(token)
    except HTTPException:
        await ws.accept()
        await ws.close(code=4404)
        return
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
                if m.get("action") == "click" and isinstance(m.get("x"), (int, float)) and isinstance(m.get("y"), (int, float)):
                    async with s["lock"]:
                        await page.mouse.click(m["x"], m["y"])
                elif m.get("action") == "mousedown" and isinstance(m.get("x"), (int, float)) and isinstance(m.get("y"), (int, float)):
                    async with s["lock"]:
                        await page.mouse.move(m["x"], m["y"])
                        await page.mouse.down()
                elif m.get("action") == "mousemove" and isinstance(m.get("x"), (int, float)) and isinstance(m.get("y"), (int, float)):
                    async with s["lock"]:
                        await page.mouse.move(m["x"], m["y"])
                elif m.get("action") == "mouseup" and isinstance(m.get("x"), (int, float)) and isinstance(m.get("y"), (int, float)):
                    async with s["lock"]:
                        await page.mouse.move(m["x"], m["y"])
                        await page.mouse.up()
                elif m.get("action") == "close":
                    break
            except asyncio.TimeoutError:
                pass

            try:
                async with s["lock"]:
                    frame = await page.screenshot(type="jpeg", quality=50)
                await ws.send_bytes(frame)
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Livestream failed")


@router.post("/process-jobs")
async def process_jobs(p: ExportRequest, tasks: BackgroundTasks):
    s = require_session(p.token)    
    page = s.get("page") if s else None

    if not page or s.get("status") not in ("success", "authenticated"):
        raise HTTPException(400, "Session is not ready or authenticated.")

    if s.get("is_processing_jobs"):
        raise HTTPException(409, "A job processing task is already running for this session.")

    s["is_processing_jobs"] = True

    async def _runner():
        try:
            async with s["lock"]:
                filter_payload = p.filters.model_dump() if p.filters else {}

                jobs = await process_jobs_task(
                    page=page, 
                    limit=p.limit,
                    max_candidates_per_job=p.max_candidates_per_job,  
                    filters=filter_payload
                )

            exports = write_exports(p.token, jobs)
            s["jobs_exported"] = len(jobs)
            s["last_export_result"] = {
                "status": "completed",
                "count": len(jobs),
                "exports": exports
            }

            try:
                await asyncio.to_thread(process_and_upload)
                logger.info("Triggered supabaser process successfully for token %s", p.token)
            except Exception as supa_err:
                logger.error("Supabaser sync failed: %s", supa_err)

        except Exception as e:
            logger.exception("Background job processing failed for token %s: %s", p.token, e)
            s["last_export_result"] = {"status": "failed", "error": str(e)}
        finally:
            s["is_processing_jobs"] = False

    tasks.add_task(_runner)

    return {
        "status": "processing",
        "token": p.token,
        "message": f"Job processing started in background for limit={p.limit}, candidates_limit={p.max_candidates_per_job}."
    }
    

@router.post("/trigger-supabaser")
async def trigger_supabaser(tasks: BackgroundTasks):
    tasks.add_task(asyncio.to_thread, process_and_upload)
    return {
        "status": "queued",
        "message": "Supabaser background processing task queued."
    }
    
    
@router.get("/export-status/{token}")
async def export_status(token: str):
    s = require_session(token)
    return {
        "token": token,
        "is_processing": s.get("is_processing_jobs", False),
        "jobs_exported": s.get("jobs_exported", 0),
        "result": s.get("last_export_result")
    }


class HandleJobsRequest(BaseModel):
    target_url: str = Field(
        default="https://httpbin.org/post",
        description="Destination URL to receive the extracted job and applicant payload via POST request."
    )
    limit: int = Field(default=10, description="Maximum number of job listings to process.")


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    try:
        from export_openapi import export_openapi_schema
        export_openapi_schema("openapi.json")
    except Exception as e:
        logger.warning("OpenAPI schema export skipped or failed: %s", e)
    yield


app = FastAPI(
    title="Kariyer Automation API",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
async def root():
    return {"status": "online"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post("/handle-jobs/{token}")
async def handle_jobs_endpoint(
    token: str, 
    req: HandleJobsRequest, 
    background_tasks: BackgroundTasks
):
    session = SESSIONS.get(token)

    if not session or not session.get("page"):
        raise HTTPException(status_code=404, detail="Active session or browser page not found for this token.")

    page = session["page"]

    if page.is_closed():
        raise HTTPException(status_code=400, detail="Browser page for this session is already closed.")

    background_tasks.add_task(
        extract_and_send_jobs,
        page=page,
        target_api_url=req.target_url,
        limit=req.limit
    )

    return {
        "status": "processing",
        "message": f"Job processing started for token {token}. Extracted data will be POSTed to {req.target_url}",
        "limit": req.limit
    }


async def tester():
    if not ENV_EMAIL or not ENV_PASSWORD:
        raise RuntimeError("KARIYER_EMAIL and KARIYER_PASSWORD environment variables are required.")

    t, s = new_session(ENV_EMAIL)

    async def snapshot_worker():
        c = 1
        while t in SESSIONS and s.get("status") not in ("success", "failed"):
            page = s.get("page")
            if page and not page.is_closed():
                try:
                    filename = f"{t}-({c}).jpg"
                    filepath = os.path.join(DEBUG_DIR, filename)
                    async with s["lock"]:
                        await page.screenshot(path=filepath, type="jpeg", quality=60)
                    logger.info("Auto-tester took screenshot: %s", filename)
                    c += 1
                except Exception as e:
                    logger.debug("Screenshot worker tick failed: %s", e)
            await asyncio.sleep(5)

    login_task = asyncio.create_task(handle_login_and_verification(t, ENV_EMAIL, ENV_PASSWORD, False, args.testerhtml))
    while not s.get("page"):
        await asyncio.sleep(0.2)

    snap_task = asyncio.create_task(snapshot_worker())
    await login_task
    snap_task.cancel()

    logger.info(json.dumps(public(SESSIONS[t])))


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
                filepath = os.path.join(DEBUG_DIR, filename)

                async with session["lock"]:
                    await page.screenshot(path=filepath, type="jpeg", quality=60)

                logger.info("Captured post-2FA screenshot (%d/%ds): %s", step, duration_seconds, filename)
            except Exception as e:
                logger.debug("Failed to take post-2FA screenshot tick %d: %s", step, e)

        await asyncio.sleep(1)

    logger.info("Completed post-2FA screenshot capture worker for token: %s", token)

if __name__ == "__main__":
    if args.autosolvetester:
        asyncio.run(tester())
    else:
        uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)