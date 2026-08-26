from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from playwright.async_api import Page, async_playwright
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("kariyer_api")

load_dotenv()

parser = argparse.ArgumentParser(description="Kariyer.net Enterprise API / Playwright Automation")
parser.add_argument("--vnc", action="store_true", help="Run the browser visibly for local debugging.")
parser.add_argument("--autosolvetester", "--test", action="store_true", help="Validate login flow and take periodic screenshots.")
args, _ = parser.parse_known_args()

ROOT = Path(__file__).resolve().parent
EXPORT_DIR = os.getenv("EXPORT_DIR", str(ROOT / "exports"))
SCREENSHOT_DIR = os.getenv("SCREENSHOT_DIR", str(ROOT / "screenshots"))
DEBUG_DIR = os.getenv("DEBUG_DIR", str(ROOT / "debug"))

for path in (SCREENSHOT_DIR, EXPORT_DIR, DEBUG_DIR):
    os.makedirs(path, exist_ok=True)

ENV_EMAIL = os.getenv("KARIYER_EMAIL", "")
ENV_PASSWORD = os.getenv("KARIYER_PASSWORD", "")

LOGIN_URL = os.getenv("KARIYER_LOGIN_URL", "https://ats.kariyer.net")
EMPLOYER_LOGIN_URL = "https://www.kariyer.net/isveren/giris"

SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", str(6 * 60 * 60)))

CHROME_PATH = os.getenv(
    "PLAYWRIGHT_CHROME",
    "/opt/pw-browsers/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell",
)

SESSIONS: dict[str, dict[str, Any]] = {}

ACTIVE_LOGIN_STATES = {
    "initiating",
    "logging_in",
    "waiting_for_captcha",
    "captcha_solved",
    "waiting_for_2fa_choice",
    "waiting_for_2fa_code",
    "awaiting_2fa_choice",
    "awaiting_2fa_code",
    "submitting_2fa",
}

SOURCE_URLS: dict[str, str | None] = {
    "active": "https://ats.kariyer.net/ilanlarim/yayindakiler",
    "passive": "https://ats.kariyer.net/ilanlarim/pasifler",
    "drafts": "https://ats.kariyer.net/ilanlarim/taslaklar",
    "archived": "https://ats.kariyer.net/ilanlarim/arsivlenmis",
    "all": None,
}

SOURCE_LABELS: dict[str, str] = {
    "active": "Yayındakiler",
    "passive": "Pasifler",
    "drafts": "Taslaklar",
    "archived": "Arşivlenmiş",
    "all": "Tümü",
}