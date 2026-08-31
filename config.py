from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("kariyer_api")

parser = argparse.ArgumentParser(description="Kariyer.net Enterprise API / Playwright Automation")
parser.add_argument(
    "--autosolvetester",
    "--test",
    action="store_true",
    help="Validate login flow and take periodic screenshots.",
)
args, _ = parser.parse_known_args()

from app.core.config import settings

ROOT = Path(__file__).resolve().parent
EXPORT_DIR = str(settings.export_dir)
SCREENSHOT_DIR = str(settings.screenshot_dir)
DEBUG_DIR = str(settings.debug_dir)

ENV_EMAIL = settings.kariyer_email
ENV_PASSWORD = settings.kariyer_password

LOGIN_URL = settings.kariyer_login_url
EMPLOYER_LOGIN_URL = "https://www.kariyer.net/isveren/giris"

SESSION_TTL_SECONDS = settings.session_ttl_seconds

CHROME_PATH = (
    settings.chrome_path
    or "/opt/pw-browsers/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell"
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
