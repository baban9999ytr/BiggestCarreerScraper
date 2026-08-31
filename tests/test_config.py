import pytest
from pydantic import ValidationError

from app.core.config import AppSettings, CaptchaProvider


def test_default_config_loading():
    s = AppSettings()
    assert s.app_env in ("development", "production", "test")
    assert s.session_ttl_seconds == 21600
    assert isinstance(s.cors_origins_list, list)
    assert len(s.cors_origins_list) > 0


def test_captcha_provider_requires_api_key():
    with pytest.raises(ValidationError) as exc_info:
        AppSettings(CAPTCHA_PROVIDER="capsolver", CAPTCHA_API_KEY="")
    assert "CAPTCHA_API_KEY must be provided" in str(exc_info.value)


def test_captcha_key_requires_provider():
    with pytest.raises(ValidationError) as exc_info:
        AppSettings(CAPTCHA_PROVIDER="none", CAPTCHA_API_KEY="some_secret_key")
    assert "CAPTCHA_PROVIDER must be explicitly set" in str(exc_info.value)


def test_cors_wildcard_rejection():
    s = AppSettings(ALLOWED_ORIGINS="*")
    with pytest.raises(ValueError) as exc_info:
        _ = s.cors_origins_list
    assert "incompatible with allow_credentials=True" in str(exc_info.value)


def test_cors_explicit_list():
    s = AppSettings(ALLOWED_ORIGINS="https://frontend.com, https://admin.com")
    assert s.cors_origins_list == ["https://frontend.com", "https://admin.com"]
