from __future__ import annotations

import logging
import os
from enum import Enum
from pathlib import Path
from typing import Any, List, Literal, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("kariyer_api.config")
ROOT_DIR = Path(__file__).resolve().parent.parent.parent


class CaptchaProvider(str, Enum):
    CAPSOLVER = "capsolver"
    NOCAPTCHA = "nocaptcha"
    NONE = "none"


class AppSettings(BaseSettings):
    # App Environment
    app_env: Literal["development", "production", "test"] = Field(
        default="development", validation_alias="APP_ENV"
    )

    # Kariyer.net Credentials
    kariyer_email: str = Field(default="", validation_alias="KARIYER_EMAIL")
    kariyer_password: str = Field(default="", validation_alias="KARIYER_PASSWORD")
    kariyer_login_url: str = Field(
        default="https://ats.kariyer.net", validation_alias="KARIYER_LOGIN_URL"
    )

    # Session & Automation Configuration
    session_ttl_seconds: int = Field(
        default=21600, validation_alias="SESSION_TTL_SECONDS"
    )
    cv_scrape_delay_seconds: int = Field(
        default=30, validation_alias="CV_SCRAPE_DELAY_SECONDS"
    )
    chrome_path: Optional[str] = Field(default=None, validation_alias="CHROME_PATH")

    # Storage Directories
    export_dir: Path = Field(
        default=ROOT_DIR / "exports", validation_alias="EXPORT_DIR"
    )
    screenshot_dir: Path = Field(
        default=ROOT_DIR / "screenshots", validation_alias="SCREENSHOT_DIR"
    )
    debug_dir: Path = Field(default=ROOT_DIR / "debug", validation_alias="DEBUG_DIR")

    supabase_url: str = Field(default="", validation_alias="SUPABASE_URL")
    supabase_key: str = Field(default="", validation_alias="SUPABASE_KEY")
    enable_telemetry: bool = Field(default=False, validation_alias="ENABLE_TELEMETRY")

    captcha_provider: CaptchaProvider = Field(
        default=CaptchaProvider.NONE, validation_alias="CAPTCHA_PROVIDER"
    )
    captcha_api_key: Optional[str] = Field(
        default=None, validation_alias="CAPTCHA_API_KEY"
    )

    allowed_origins: str = Field(default="", validation_alias="ALLOWED_ORIGINS")

    # Format: http://user:pass@host:port  or  http://host:port
    # Leave unset (default) to disable proxy.
    outbound_proxy: Optional[str] = Field(
        default=None, validation_alias="OUTBOUND_PROXY"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("export_dir", "screenshot_dir", "debug_dir")
    @classmethod
    def ensure_directories(cls, v: Path) -> Path:
        v.mkdir(parents=True, exist_ok=True)
        return v

    @model_validator(mode="before")
    @classmethod
    def map_legacy_captcha_keys(cls, data: dict[str, Any]) -> dict[str, Any]:
        provider = data.get("CAPTCHA_PROVIDER") or os.getenv("CAPTCHA_PROVIDER")
        api_key = data.get("CAPTCHA_API_KEY") or os.getenv("CAPTCHA_API_KEY")

        if not provider or not api_key:
            nocaptcha_key = data.get("NO_CAPTCHA_AI_KEY") or os.getenv(
                "NO_CAPTCHA_AI_KEY"
            )
            capsolver_key = data.get("CAPSOLVER_API_KEY") or os.getenv(
                "CAPSOLVER_API_KEY"
            )

            if capsolver_key:
                logger.warning(
                    "Legacy CAPSOLVER_API_KEY detected. Use CAPTCHA_PROVIDER=capsolver and CAPTCHA_API_KEY."
                )
                data["CAPTCHA_PROVIDER"] = CaptchaProvider.CAPSOLVER
                data["CAPTCHA_API_KEY"] = capsolver_key
            elif nocaptcha_key:
                logger.warning(
                    "Legacy NO_CAPTCHA_AI_KEY detected. Use CAPTCHA_PROVIDER=nocaptcha and CAPTCHA_API_KEY."
                )
                data["CAPTCHA_PROVIDER"] = CaptchaProvider.NOCAPTCHA
                data["CAPTCHA_API_KEY"] = nocaptcha_key

        return data

    @model_validator(mode="after")
    def validate_captcha_config(self) -> "AppSettings":
        if self.captcha_provider != CaptchaProvider.NONE and not self.captcha_api_key:
            raise ValueError(
                f"CAPTCHA_API_KEY must be provided when CAPTCHA_PROVIDER is set to '{self.captcha_provider.value}'."
            )
        if self.captcha_api_key and self.captcha_provider == CaptchaProvider.NONE:
            raise ValueError(
                "CAPTCHA_PROVIDER must be explicitly set (e.g. 'capsolver' or 'nocaptcha') when CAPTCHA_API_KEY is provided."
            )
        return self

    @property
    def cors_origins_list(self) -> List[str]:
        raw = self.allowed_origins.strip()
        if raw == "*":
            raise ValueError(
                "ALLOWED_ORIGINS contains '*'. This is incompatible with "
                "allow_credentials=True. List explicit origins instead."
            )

        origins = [o.strip() for o in raw.split(",") if o.strip()]
        if not origins:
            if self.app_env == "production":
                raise RuntimeError(
                    "ALLOWED_ORIGINS is not set in production mode. "
                    "Refusing to start with an empty CORS allowlist."
                )
            return [
                "http://localhost",
                "http://localhost:3000",
                "http://localhost:5173",
                "http://localhost:8000",
                "http://127.0.0.1:8000",
            ]
        return origins


settings = AppSettings()
