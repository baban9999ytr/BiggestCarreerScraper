import base64
import logging
import os
import re
import subprocess
import sys
from logging import Formatter, LogRecord

import requests
from packaging.version import parse as parse_version

from app.core.config import settings

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

_TOKEN_REGEX = re.compile(r"([a-fA-F0-9]{32})")
_EMAIL_REGEX = re.compile(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)")
_VERSION_FALLBACK_REGEX = re.compile(r'^\s*version\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


class SecretRedactingFormatter(Formatter):
    def format(self, record: LogRecord) -> str:
        msg = super().format(record)
        msg = _TOKEN_REGEX.sub(r"***\g<1>[...]", msg)
        msg = _EMAIL_REGEX.sub(r"***@***", msg)
        return msg


def setup_logging() -> None:
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler()
    formatter = SecretRedactingFormatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s")
    handler.setFormatter(formatter)

    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO if settings.app_env != "development" else logging.DEBUG)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)

GITHUB_OWNER = "baban9999ytr"
GITHUB_REPO = "BiggestCarreerScraper"
BRANCH = "main"


def parse_toml_version(toml_content: str) -> str | None:
    """Parses pyproject.toml content using TOML parser with a multiline regex fallback."""
    if tomllib:
        try:
            parsed = tomllib.loads(toml_content)
            return parsed.get("project", {}).get("version")
        except Exception:
            pass

    match = _VERSION_FALLBACK_REGEX.search(toml_content)
    return match.group(1) if match else None


def get_system_github_token() -> str | None:
    try:
        token = subprocess.check_output(
            ["gh", "auth", "token"], stderr=subprocess.DEVNULL, text=True
        ).strip()
        if token:
            return token
    except Exception:
        pass

    try:
        credential_data = subprocess.check_output(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            stderr=subprocess.DEVNULL,
            text=True,
        )
        for line in credential_data.splitlines():
            if line.startswith("password="):
                pass_val = line.split("=", 1)[1].strip()
                if pass_val:
                    return pass_val
    except Exception:
        pass

    return os.getenv("GITHUB_TOKEN")


def get_local_version() -> str | None:
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "..", "..", "pyproject.toml"),
        os.path.join(os.getcwd(), "pyproject.toml"),
    ]

    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    ver = parse_toml_version(f.read())
                    if ver:
                        return ver
            except Exception:
                pass
    return None


def _log_auth_warning(reason: str) -> None:
    logger.warning(
        "\n" + "!" * 70 + "\n"
        "  [!] AUTHENTICATION / ACCESS WARNING\n"
        f"  {reason}\n"
        "  Skipping automatic version verification.\n"
        "  [!] YOU ARE AT RISK OF RUNNING WITH AN OUTDATED / MISMATCHED VERSION.\n"
        "  Please configure Git/GitHub CLI credentials or set GITHUB_TOKEN.\n" + "!" * 70
    )


def check_for_updates() -> None:
    local_version_str = get_local_version()
    if not local_version_str:
        logger.debug("Could not determine local pyproject.toml version. Skipping update check.")
        return

    api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/pyproject.toml?ref={BRANCH}"
    headers = {"Accept": "application/vnd.github.v3+json"}

    token = get_system_github_token()
    if not token:
        _log_auth_warning("No GitHub account or token found in the environment.")
        return

    headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.get(api_url, headers=headers, timeout=4.0)

        if response.status_code in (401, 403):
            _log_auth_warning(
                f"GitHub returned HTTP {response.status_code} (Unauthorized / Access Forbidden)."
            )
            return
        elif response.status_code == 404:
            logger.warning("Remote pyproject.toml not found or repository access is restricted.")
            return
        elif response.status_code != 200:
            logger.debug(f"GitHub version check failed with status {response.status_code}")
            return

        content_b64 = response.json().get("content", "").replace("\n", "").replace("\r", "")
        remote_file_content = base64.b64decode(content_b64).decode("utf-8")

        remote_version_str = parse_toml_version(remote_file_content)
        if not remote_version_str:
            logger.debug("Could not parse version from remote pyproject.toml.")
            return

        try:
            is_outdated = parse_version(remote_version_str) > parse_version(local_version_str)
        except Exception:
            is_outdated = remote_version_str != local_version_str

        if is_outdated:
            logger.warning(
                "\n" + "=" * 70 + "\n"
                "  [!] UPDATE AVAILABLE\n"
                f"  Your local version (v{local_version_str}) is outdated.\n"
                f"  Latest upstream version on '{GITHUB_OWNER}/{GITHUB_REPO}' is (v{remote_version_str}).\n"
                "  Please pull the latest changes or re-download the source.\n" + "=" * 70
            )
        else:
            logger.info(f"App is up to date (v{local_version_str}).")

    except requests.RequestException:
        logger.debug("Network error while checking for updates.")
    except Exception as err:
        logger.debug(f"Unexpected update check error: {err}")


setup_logging()
check_for_updates()
