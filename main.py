from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.api_router import api_router
from app.core.browser_manager import browser_manager
from app.core.config import settings
from app.core.cors import get_allowed_origins
from app.core.logger import setup_logging
from app.core.metadata_store import metadata_store
from app.models.session import new_session, public
from automation import handle_login_and_verification
from config import SESSIONS, args

setup_logging()
logger = logging.getLogger("main")

GEEKED_PATH = os.path.join(
    os.path.expanduser("~"), "Desktop", "LastRodeo", "GeekedTest"
)
if os.path.exists(GEEKED_PATH):
    sys.path.append(GEEKED_PATH)


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    await metadata_store.init_db()
    SESSIONS.update(await metadata_store.get_all_sessions())

    try:
        from app.core.openapi import export_openapi_schema

        export_openapi_schema("openapi.json")
    except Exception as e:
        logger.warning("OpenAPI schema export skipped or failed: %s", e)

    yield

    logger.info("Shutting down... cleaning up browser sessions.")
    await browser_manager.terminate_all()


app = FastAPI(
    title="Kariyer Automation API",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)

app.include_router(api_router)


async def tester():
    if not settings.kariyer_email or not settings.kariyer_password:
        raise RuntimeError(
            "KARIYER_EMAIL and KARIYER_PASSWORD environment variables are required."
        )

    t, s = new_session(settings.kariyer_email)

    async def snapshot_worker():
        c = 1
        while t in SESSIONS and s.get("status") not in ("success", "failed"):
            page = s.get("page")
            if page and not page.is_closed():
                try:
                    filename = f"{t}-({c}).jpg"
                    filepath = os.path.join(str(settings.debug_dir), filename)
                    async with s["lock"]:
                        await page.screenshot(path=filepath, type="jpeg", quality=60)
                    logger.info("Auto-tester took screenshot: %s", filename)
                    c += 1
                except Exception as e:
                    logger.debug("Screenshot worker tick failed: %s", e)
            await asyncio.sleep(5)

    login_task = asyncio.create_task(
        handle_login_and_verification(
            t,
            settings.kariyer_email,
            settings.kariyer_password,
            False,
            getattr(args, "testerhtml", False),
        )
    )
    while not s.get("page"):
        await asyncio.sleep(0.2)

    snap_task = asyncio.create_task(snapshot_worker())
    await login_task
    snap_task.cancel()

    logger.info(json.dumps(public(SESSIONS[t])))


if __name__ == "__main__":
    if args.autosolvetester:
        asyncio.run(tester())
    else:
        uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)  # noqa: S104
