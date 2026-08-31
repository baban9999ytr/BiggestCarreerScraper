from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import json

import logging
import os
import re
import random
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp
import cv2
import numpy as np
import uvicorn
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from playwright.async_api import Page, async_playwright
from pydantic import BaseModel, Field

try:
    import ddddocr
    _ocr = ddddocr.DdddOcr(det=False, ocr=False, show_ad=False)
except Exception:
    _ocr = None

sys.path.append(r"C:\Users\KRR\Desktop\LastRodeo\GeekedTest")
try:
    from geeked import Geeked
except ImportError as e:
    Geeked = None
    logging.getLogger("main").warning("GeekedTest not found. Auto-captcha disabled: %s", e)

from config import SESSIONS, ACTIVE_LOGIN_STATES, logger, DEBUG_DIR, LOGIN_URL, args
from automation_process_jobs import extract_current_job, process_jobs_task, install_overlay_killer


def aid(element_id: str) -> str:
    return f'[id="{element_id}"]'


from app.core.config import settings
_TR_MAP = str.maketrans({
    "I": "i", "İ": "i", "ı": "i",
    "Ş": "s", "ş": "s",
    "Ğ": "g", "ğ": "g",
    "Ü": "u", "ü": "u",
    "Ö": "o", "ö": "o",
    "Ç": "c", "ç": "c",
})
NO_CAPTCHA_AI_KEY = settings.captcha_api_key

_SEND_CODE_LABELS = [
    "Doğrulama kodunu gönder",
    "Doğrulama kodunu gönder",
    "Doğrulama kodu gönder",
]
_RESEND_LABELS = ["Tekrar gönder", "Tekrar gönder", "Tekrar gönder"]
_SMS_SWITCH_LABELS = [
    "SMS ile doğrulama yapın",
    "SMS ile doğrulama yapın",
    "SMS ile doğrulama yapın",
]
_EMAIL_SWITCH_LABELS = [
    "E-posta ile doğrulama yapın",
    "E-posta ile doğrulama yapın",
    "E-posta ile doğrulama yapın",
]
_VERIFY_LABELS = ["Doğrula"]


def norm_text(s: str) -> str:
    if not s:
        return ""
    return " ".join(s.replace("\u0307", "").translate(_TR_MAP).lower().split())


def page_url(page: Page) -> str:
    try:
        return page.url or ""
    except Exception:
        return ""


def url_implies_2fa(url: str) -> bool:
    u = (url or "").lower()
    return any(x in u for x in ("eposta-2fa", "sms-2fa", "telefon-2fa", "/2fa", "2fa"))


def url_implies_authenticated(url: str) -> bool:
    u = (url or "").lower()
    if not u or url_implies_2fa(u):
        return False
    if "/giris" in u or "/login" in u:
        return False
    if "eposta" in u or "sms" in u or "telefon" in u or "dogrulama" in u:
        return False
    return False


_CLICK_VISIBLE_JS = r"""
({ tag, needles, exact }) => {
  const isShown = (el) => {
    if (!el) return false;
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden' || Number(st.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 8 && r.height > 8;
  };
  const norm = (s) => (s || '')
    .replace(/\u0307/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
    .replace(/ı/g, 'i').replace(/ş/g, 's').replace(/ğ/g, 'g')
    .replace(/ü/g, 'u').replace(/ö/g, 'o').replace(/ç/g, 'c');
  const wanted = (needles || []).map(norm);
  const cards = [...document.querySelectorAll('.card-wrapper, .card-wrapper, .auth-new')].filter(isShown);
  const roots = cards.length ? cards : [document.body];
  const visible = [];
  for (const root of roots) {
    for (const el of root.querySelectorAll(tag)) {
      if (!isShown(el)) continue;
      const raw = (el.textContent || '').replace(/\s+/g, ' ').trim();
      visible.push(raw);
      const t = norm(raw);
      const hit = exact ? wanted.includes(t) : wanted.some((n) => t.includes(n));
      if (hit) {
        el.click();
        return { ok: true, text: raw };
      }
    }
  }
  return { ok: false, visible };
}
"""


async def any_visible(page: Page, selector: str) -> bool:
    try:
        loc = page.locator(selector)
        count = await loc.count()
        for i in range(count):
            try:
                if await loc.nth(i).is_visible():
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


async def captcha_visible(page: Page) -> bool:
    if url_implies_2fa(page_url(page)):
        return False
    try:
        if await page.locator(
            ".geetest_success, .geetest_radar_success, .geetest_wait_success, "
            ".geetest_panel_success, [class*='geetest'][class*='success']"
        ).count():
            success_shown = False
            loc = page.locator(
                ".geetest_success, .geetest_radar_success, .geetest_wait_success, "
                ".geetest_panel_success, [class*='geetest'][class*='success']"
            )
            for i in range(await loc.count()):
                try:
                    if await loc.nth(i).is_visible():
                        success_shown = True
                        break
                except Exception:
                    continue
            if success_shown:
                return False
    except Exception:
        pass
    selector = (
        ".geetest_holder, .geetest_box, .geetest_box_wrap, .geetest_container, "
        ".geetest_window, .geetest_popup_box, .geetest_panel, .geetest_widget, "
        "[class*='geetest'], iframe[src*='geetest'], iframe[src*='captcha'], "
        ".geetest_btn, .geetest_radar_tip"
    )
    try:
        elements = page.locator(selector)
        count = await elements.count()
        for i in range(count):
            el = elements.nth(i)
            try:
                if not await el.is_visible():
                    continue
                box = await el.bounding_box()
                if box and box["width"] >= 40 and box["height"] >= 40:
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


async def read_login_error(page: Page) -> Optional[str]:
    selectors = (
        ".alert-danger,.validation-summary-errors,.field-validation-error,"
        ".toast-error,.notification-error,[role='alert']"
    )
    try:
        texts = await page.locator(selectors).all_inner_texts()
        text = " ".join(x.strip() for x in texts if x.strip())
        if text:
            return re.sub(r"\s+", " ", text)
    except Exception:
        pass
    try:
        body = await page.locator("body").inner_text(timeout=1000)
        for marker in (
            "Oturum açma başarısız",
            "Giriş başarısız",
            "Kullanıcı adı veya şifre",
            "şifre hatalı",
            "hesabınız kilitlendi",
        ):
            if marker.lower() in body.lower():
                line = next((x.strip() for x in body.splitlines() if marker.lower() in x.lower()), marker)
                return re.sub(r"\s+", " ", line)
    except Exception:
        pass
    return None


async def login_form_visible(page: Page) -> bool:
    return await any_visible(page, "#loginNameFormInput") and await any_visible(page, "form button[type='submit']")


async def is_user_logged_in(page: Page) -> bool:
    logged_in_selectors = [
        "#user-info",
        "#dashboard-job-list",
        "#dashboard-articles-list",
        ".wide-card.job-card",
        ".page-view",
    ]

    for selector in logged_in_selectors:
        try:
            locator = page.locator(selector).first
            if await locator.is_visible(timeout=700):
                return True
        except Exception:
            continue

    return False


async def click_left_corner_to_dismiss_overlay(page: Page) -> None:
   
    try:
        viewport = await page.evaluate(
            """() => ({
                width: window.innerWidth,
                height: window.innerHeight
            })"""
        )

        width = int(viewport["width"])
        height = int(viewport["height"])

        x = random.randint(4, min(25, max(4, width - 1)))
        y = random.randint(
            max(4, height - 25),
            max(4, height - 4),
        )

        logger.info("Attempting backdrop-dismiss click at x=%d, y=%d", x, y)
        await page.mouse.click(x, y)
        await page.wait_for_timeout(400)

    except Exception as e:
        logger.debug("Corner click skipped: %s", e)


async def post_login_cleanup(page: Page) -> bool:
   
    for _ in range(30):  
        if await is_user_logged_in(page):
            logger.info("Authenticated dashboard detected after login/2FA.")

            await dismiss_overlays(page)
            await click_left_corner_to_dismiss_overlay(page)

            await page.wait_for_timeout(800)
            return await is_user_logged_in(page)

        await page.wait_for_timeout(1000)

    logger.warning("Authenticated dashboard was not detected after 2FA.")
    return False


async def detect_2fa_card(page: Page) -> Optional[str]:
    if await any_visible(page, "button:has-text('DEVAM ET')") or await any_visible(page, "text=Hesabınız doğrulandı"):
        return "devam_et"
    if await any_visible(page, aid("2faCodeFormInput")) or await any_visible(page, aid("2faCodeFormGroup")) or await any_visible(page, aid("2faCode")):
        return "code_entry"
    if await any_visible(page, aid("2faPhoneFormInput")) or await any_visible(page, aid("2faPhoneFormGroup")) or await any_visible(page, aid("2faPhone")):
        return "sms_send"
    if await any_visible(page, aid("2faEmailFormInput")) or await any_visible(page, aid("2faEmailFormGroup")) or await any_visible(page, aid("2faEmail")):
        return "email_send"
    if await any_visible(page, "img[alt*='sms' i], img[alt*='phone' i]"):
        return "sms_send"
    if await any_visible(page, "img[alt*='paper' i]"):
        return "code_entry"
    if await any_visible(page, "img[alt*='mail' i]"):
        return "email_send"
    return None


async def twofa_visible(page: Page) -> bool:
    if url_implies_2fa(page_url(page)):
        return True
    card = await detect_2fa_card(page)
    if card:
        return True
    if await any_visible(page, ".auth-new .card-wrapper, .auth-new, .page-view.auth-new, .card-wrapper"):
        return True

    probes = [
        aid("2faEmail"), aid("2faCode"), aid("2faPhone"),
        "text=Lütfen hesabınızı doğrulayın",
        "text=SMS ile doğrulama yapın",
        "text=E-posta ile doğrulama yapın",
        "text=Doğrulama kodunu gönder",
        "text=doğrulama kodunu girin",
        "text=6 Haneli Doğrulama Kodu",
        "h2:has-text('hesabınızı doğrulayın')",
        "h2:has-text('doğrulama kodunu girin')",
        "button:has-text('DEVAM ET')"
    ]
    for sel in probes:
        if await any_visible(page, sel):
            return True

    try:
        body = await page.locator("body").inner_text(timeout=1000)
    except Exception:
        return False
    body_l = body.lower()
    needles = (
        "lütfen hesabınızı doğrulayın",
        "sms ile doğrulama yapın",
        "e-posta ile doğrulama yapın",
        "doğrulama kodunu gönder",
        "doğrulama kodunu girin",
        "6 haneli doğrulama kodu",
        "hesabınız doğrulandı"
    )
    return any(n in body_l for n in needles)


async def authenticated_visible(page: Page) -> bool:
    url = page_url(page).lower()
    if url_implies_2fa(url) or "/giris" in url or "/login" in url:
        return False
    if await twofa_visible(page) or await login_form_visible(page):
        return False
    if await captcha_visible(page):
        return False

    if await is_user_logged_in(page):
        return True

    try:
        if await page.locator(".job-list-new, a[href*='ilan'], a[href*='aday'], text=İlanlarım, text=Yayındaki İlanlar").first.is_visible(timeout=1000):
            return True
    except Exception:
        pass
    return False


async def classify_screen(page: Page) -> str:
    url = page_url(page)
    if await twofa_visible(page) or url_implies_2fa(url):
        return "2fa"
    if await captcha_visible(page):
        return "captcha"
    if await login_form_visible(page):
        err = await read_login_error(page)
        if err:
            return "error"
        return "login"
    if await authenticated_visible(page):
        return "authenticated"
    err = await read_login_error(page)
    if err and ("/giris" in url.lower() or "/login" in url.lower()):
        return "error"
    return "transition"


async def save_debug_artifacts(page: Page, s: dict[str, Any], label: str) -> None:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", label).strip("_") or "debug"
    stem = f"{s['token']}_{safe}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    screenshot_path = os.path.join(DEBUG_DIR, f"{stem}.jpg")
    html_path = os.path.join(DEBUG_DIR, f"{stem}.html")
    try:
        await page.screenshot(path=screenshot_path, type="jpeg", quality=70, full_page=True)
    except Exception:
        screenshot_path = ""
    try:
        html = await page.content()
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception:
        html_path = ""
    s["debug_artifacts"] = {k: v for k, v in {"screenshot": screenshot_path, "html": html_path}.items() if v}


async def wait_login_outcome(page: Page, s: dict[str, Any], timeout: float = 60) -> str:
    deadline = asyncio.get_running_loop().time() + timeout
    last_kind = None
    while asyncio.get_running_loop().time() < deadline:
        try:
            s["last_url"] = page.url
        except Exception:
            pass
        kind = await classify_screen(page)
        s["screen"] = kind
        if kind == "2fa":
            s["2fa_card"] = await detect_2fa_card(page)
        if kind != last_kind:
            logger.info("Screen classified as %s url=%s card=%s", kind, s.get("last_url"), s.get("2fa_card"))
            last_kind = kind
        if kind == "2fa":
            return "2fa"
        if kind == "captcha":
            return "captcha"
        if kind == "error":
            s["error"] = await read_login_error(page)
            await save_debug_artifacts(page, s, "login_rejected")
            return "error"
        if kind == "authenticated":
            return "authenticated"
        await asyncio.sleep(0.4)

    kind = await classify_screen(page)
    s["screen"] = kind
    if kind in ("2fa", "captcha", "authenticated", "login", "transition"):
        return kind
    if kind == "error":
        s["error"] = await read_login_error(page)
        return "error"
    s["error"] = "Login outcome was not detected within timeout."
    await save_debug_artifacts(page, s, "login_timeout")
    return "timeout"


async def first_visible(page: Page, selector: str) -> Optional[Any]:
    loc = page.locator(selector)
    try:
        count = await loc.count()
    except Exception:
        return None
    for i in range(count):
        nth = loc.nth(i)
        try:
            if await nth.is_visible(timeout=300):
                return nth
        except Exception:
            continue
    return None


async def visible_by_norm_text(page: Page, tag: str, wanted: str, exact: bool = True) -> Optional[Any]:
    target = norm_text(wanted)
    loc = page.locator(tag)
    try:
        count = await loc.count()
    except Exception:
        return None
    for i in range(count):
        el = loc.nth(i)
        try:
            if not await el.is_visible(timeout=300):
                continue
            raw = await el.text_content()
            got = norm_text(raw or "")
            if exact and got == target:
                return el
            if not exact and target in got:
                return el
        except Exception:
            continue
    return None


async def visible_button_exact_text(page: Page, exact_text: str) -> Optional[Any]:
    buttons = page.locator("button")
    count = await buttons.count()
    
    for i in range(count):
        btn = buttons.nth(i)
        try:
            if await btn.is_visible():
                text = (await btn.text_content() or "").strip()
                if text == exact_text.strip():
                    return btn
        except Exception:
            continue
            
    return await visible_by_norm_text(page, "button", exact_text, exact=True)


async def force_click_element(page: Page, locator: Any) -> bool:
    if locator is None:
        return False

    try:
        await locator.click(force=True, timeout=3000)
        return True
    except Exception as e:
        logger.warning("Playwright click failed, executing JavaScript DOM force-click fallback: %s", e)

    try:
        handle = await locator.element_handle() if hasattr(locator, "element_handle") else locator
        if handle:
            await handle.evaluate("""(el) => {
                    el.removeAttribute('disabled');
                el.disabled = false;
                el.classList.remove('disabled');

                // Dispatch synthetic events
                const events = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
                events.forEach(eventType => {
                    const evt = new MouseEvent(eventType, {
                        bubbles: true,
                        cancelable: true,
                        view: window
                    });
                    el.dispatchEvent(evt);
                });
            }""")
            return True
    except Exception as err:
        logger.error("JS DOM force-click fallback failed: %s", err)

    return False


async def click_in_visible_card(page: Page, tag: str, texts: list[str], exact: bool = True) -> dict[str, Any]:
    for t in texts:
        el = await visible_by_norm_text(page, tag, t, exact=exact)
        if el is not None:
            try:
                await el.click(force=True)
                logger.info("Clicked visible %s %r", tag, t)
                return {"ok": True, "text": t, "via": "playwright"}
            except Exception as e:
                logger.warning("Playwright click failed on %s %r: %s", tag, t, e)
    try:
        result = await page.evaluate(_CLICK_VISIBLE_JS, {"tag": tag, "needles": texts, "exact": exact})
    except Exception as e:
        logger.warning("JS card click failed: %s", e)
        return {"ok": False, "visible": []}
    return result or {"ok": False}


async def fill_vue_input(locator: Any, value: str) -> None:
    try:
        await locator.click(force=True)
    except Exception:
        pass
    try:
        await locator.fill("")
    except Exception:
        pass
    handle = None
    try:
        handle = await locator.element_handle()
    except Exception:
        handle = None
    if handle is not None:
        await handle.evaluate(
            """(el, v) => {
                const desc = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                );
                desc.set.call(el, v);
                el.dispatchEvent(new InputEvent('input', { bubbles: true, data: v, inputType: 'insertText' }));
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: '0' }));
            }""",
            value,
        )
    else:
        await locator.fill(value)


async def wait_for_card(page: Page, wanted: str, timeout: float = 15) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if await detect_2fa_card(page) == wanted:
            return True
        await asyncio.sleep(0.3)
    return await detect_2fa_card(page) == wanted


async def _link_visible(page: Page, labels: list[str]) -> bool:
    for label in labels:
        if await visible_by_norm_text(page, "a", label, exact=False):
            return True
    return False


async def current_2fa_channel(page: Page) -> Optional[str]:
    if await _link_visible(page, _SMS_SWITCH_LABELS):
        return "email"
    if await _link_visible(page, _EMAIL_SWITCH_LABELS):
        return "sms"
    card = await detect_2fa_card(page)
    if card == "sms_send":
        return "sms"
    if card == "email_send":
        return "email"
    return None


async def switch_2fa_channel(page: Page, method: str) -> bool:
    channel = await current_2fa_channel(page)
    if channel is None or channel == method:
        return False
    if method == "sms":
        clicked = await click_in_visible_card(page, "a", _SMS_SWITCH_LABELS, exact=False)
        if clicked.get("ok"):
            await wait_for_card(page, "sms_send", timeout=8)
            return True
        return False
    if method == "email":
        clicked = await click_in_visible_card(page, "a", _EMAIL_SWITCH_LABELS, exact=False)
        if clicked.get("ok"):
            await wait_for_card(page, "email_send", timeout=8)
            return True
        return False
    return False


async def submit_login_form(page: Page, email: str, password: str) -> None:
    user_input = page.locator("#loginNameFormInput")
    pass_input = page.locator("#passwordFormInput")

    await user_input.click(force=True)
    await user_input.fill(email)
    
    await pass_input.click(force=True)
    await pass_input.fill(password)

    await page.wait_for_timeout(1000)
    await page.get_by_role("button", name="Giriş Yap").click()
    await page.wait_for_timeout(1000)


async def wait_and_click_devam_et(page: Page, timeout: float = 12.0) -> bool:
    """Waits for the 'DEVAM ET' button to appear and clicks it if found."""
    deadline = asyncio.get_running_loop().time() + timeout
    devam_btn = page.get_by_role("button", name="DEVAM ET")
    while asyncio.get_running_loop().time() < deadline:
        try:
            if await devam_btn.is_visible():
                await devam_btn.click(force=True)
                logger.info("Found and clicked 'DEVAM ET' button.")
                return True
        except Exception:
            pass
        await asyncio.sleep(0.4)
    return False


async def do_2fa(page: Page, s: dict[str, Any]) -> bool:
    for _ in range(50):
        if await detect_2fa_card(page) or await twofa_visible(page) or url_implies_2fa(page_url(page)):
            break
        await asyncio.sleep(0.2)

    s["2fa_card"] = await detect_2fa_card(page)
    s["screen"] = "2fa"
    s["status"] = "waiting_for_2fa_choice"

    last_consumed_code = None

    while True:
        if await authenticated_visible(page):
            logger.info("Left 2FA into authenticated ATS (%s).", page_url(page))
            await post_login_cleanup(page)
            return True

        card = await detect_2fa_card(page)
        s["2fa_card"] = card
        s["last_url"] = page_url(page)
        s["screen"] = "2fa"
        method = s["2fa_method"]

        if card == "devam_et":
            if await wait_and_click_devam_et(page, timeout=3.0):
                await page.wait_for_timeout(2000)
                if await authenticated_visible(page) or await wait_login_outcome(page, s, timeout=20) == "authenticated":
                    await post_login_cleanup(page)
                    return True

        if s.get("2fa_resend"):
            s["2fa_resend"] = False
            clicked = await click_in_visible_card(page, "a", _RESEND_LABELS, exact=False)
            if not clicked.get("ok"):
                await click_in_visible_card(page, "button", _SEND_CODE_LABELS, exact=False)
            s["2fa_code"] = None
            last_consumed_code = None
            s["status"] = "waiting_for_2fa_code"
            s["error"] = None
            await wait_for_card(page, "code_entry", timeout=12)
            continue

        if card in ("email_send", "sms_send", None) and card not in ("code_entry", "devam_et"):
            s["status"] = "waiting_for_2fa_choice"
            if method not in ("email", "sms"):
                await asyncio.sleep(0.25)
                continue
            if await switch_2fa_channel(page, method):
                continue
            clicked = await click_in_visible_card(page, "button", _SEND_CODE_LABELS, exact=False)
            if clicked.get("ok"):
                await wait_for_card(page, "code_entry", timeout=12)
            else:
                await asyncio.sleep(0.4)
            continue

        if method in ("email", "sms") and await switch_2fa_channel(page, method):
            continue

        s["status"] = "waiting_for_2fa_code"
        code = s.get("2fa_code")
        if not code or code == last_consumed_code:
            await asyncio.sleep(0.25)
            continue

        last_consumed_code = code

        code_input = None
        for _ in range(20):
            code_input = await first_visible(page, aid("2faCodeFormInput"))
            if code_input is not None:
                break
            await asyncio.sleep(0.3)
        if code_input is None:
            s["2fa_code"] = None
            last_consumed_code = None
            continue

        await fill_vue_input(code_input, code)
        await page.wait_for_timeout(500)

        verify_btn = None
        for label in _VERIFY_LABELS:
            verify_btn = await visible_button_exact_text(page, label)
            if verify_btn is not None:
                break

        if verify_btn is None:
            verify_btn = page.locator("button:has-text('Doğrula')").first

        clicked = await force_click_element(page, verify_btn)
        if not clicked:
            await click_in_visible_card(page, "button", ["Doğrula"], exact=False)

        devam_et_found = await wait_and_click_devam_et(page, timeout=12.0)

        if devam_et_found:
            outcome = await wait_login_outcome(page, s, timeout=25)
            if outcome == "authenticated" or await authenticated_visible(page):
                await post_login_cleanup(page)
                return True
            if outcome == "captcha":
                outcome = await hold_for_captcha_then_continue(page, s)
                if outcome == "authenticated":
                    await post_login_cleanup(page)
                    return True
        else:
            logger.warning("2FA verification failed: 'DEVAM ET' button did not appear.")
            s["error"] = "2FA verification failed or 'DEVAM ET' button did not appear."
            s["2fa_code"] = None
            last_consumed_code = None
            s["status"] = "waiting_for_2fa_code"
            await asyncio.sleep(0.6)
            
            
            
            
async def _start_html_dumper_loop(token: str, interval: int = 10):
    """Playwright sayfası oluştuğu andan itibaren her 10 saniyede bir HTML'i kaydeder."""
    session = SESSIONS.get(token)
    if not session:
        return

    logger.info("HTML dumper worker started immediately for token: %s", token)
    counter = 1

    while token in SESSIONS and session.get("status") not in ("closed", "failed"):
        page = session.get("page")
        if page and not page.is_closed():
            try:
                async with session["lock"]:
                    html_content = await page.content()

                filename = f"dom-{token}-{counter:03d}.html"
                filepath = os.path.join(DEBUG_DIR, filename)

                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(html_content)

                logger.info("HTML dumper saved DOM state: %s", filename)
                counter += 1
            except Exception as e:
                logger.debug("HTML dumper tick error for token %s: %s", token, e)

        await asyncio.sleep(interval)
        
        
        

async def hold_for_captcha_then_continue(page: Page, s: dict[str, Any]) -> str:
    
    s["status"] = "waiting_for_captcha"
    s["screen"] = "captcha"
    logger.info("CAPTCHA detected! Attempting automatic Geetest bypass...")
    last_url = page_url(page)

    solve_success = await auto_solve_and_submit(page)
    if solve_success:
        await page.wait_for_timeout(2000)

    while True:
        url = page_url(page)
        if url != last_url:
            last_url = url
            s["last_url"] = url

        kind = await classify_screen(page)
        s["screen"] = kind

        if kind == "2fa" or url_implies_2fa(url):
            s["2fa_card"] = await detect_2fa_card(page)
            s["status"] = "waiting_for_2fa_choice"
            return "2fa"

        if kind == "authenticated":
            await post_login_cleanup(page)
            return "authenticated"

        if kind == "error":
            s["error"] = await read_login_error(page)
            await save_debug_artifacts(page, s, "login_rejected")
            return "error"

        if kind != "captcha":
            card = await detect_2fa_card(page)
            if card or await twofa_visible(page):
                s["2fa_card"] = card
                s["status"] = "waiting_for_2fa_choice"
                return "2fa"

            s["status"] = "captcha_solved"
            nxt = await wait_login_outcome(page, s, timeout=90)
            if nxt in ("2fa", "captcha", "authenticated", "error"):
                if nxt == "authenticated":
                    await post_login_cleanup(page)
                return nxt
            continue

        await asyncio.sleep(0.4)


async def hold_for_post_login(page: Page, s: dict[str, Any], email: str = "", password: str = "") -> str:
    s["status"] = "logging_in"
    last_submit = asyncio.get_running_loop().time()
    while True:
        kind = await classify_screen(page)
        s["screen"] = kind
        s["last_url"] = page_url(page)
        if kind == "captcha":
            return await hold_for_captcha_then_continue(page, s)
        if kind == "2fa":
            s["2fa_card"] = await detect_2fa_card(page)
            s["status"] = "waiting_for_2fa_choice"
            return "2fa"
        if kind == "authenticated":
            await post_login_cleanup(page)
            return "authenticated"
        if kind == "error":
            s["error"] = await read_login_error(page)
            return "error"
        now = asyncio.get_running_loop().time()
        if kind == "login" and email and password and now - last_submit > 20:
            await submit_login_form(page, email, password)
            last_submit = now
        await asyncio.sleep(0.5)


async def handle_login_and_verification(
    token: str, 
    email: str, 
    password: str, 
    keep_alive: bool = True,
    testerhtml: bool = False
) -> None:
    s = SESSIONS[token]
    pw = browser = context = None
    try:
        s.update(status="logging_in", error=None)
        pw = await async_playwright().start()

        is_testerhtml = testerhtml or ("--testerhtml" in sys.argv)

        is_headless = not is_testerhtml

        browser = await pw.chromium.launch(
            headless=False, 
            # headless=is_headless, 
            args=["--no-sandbox", "--disable-gpu"]
        )

        from app.core.proxy import get_playwright_proxy
        _proxy_cfg = get_playwright_proxy()
        context = await browser.new_context(
            viewport={"width": 1280, "height": 1024},
            locale="tr-TR",
            **( {"proxy": _proxy_cfg} if _proxy_cfg else {} ),
        )
        await install_overlay_killer(context)

        page = await context.new_page()
        page.set_default_timeout(15000)
        s.update(playwright=pw, browser=browser, context=context, page=page)

        if is_testerhtml:
            asyncio.create_task(_start_html_dumper_loop(token, 10))

        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_selector("#loginNameFormInput", timeout=30000)

        outcome = "login"
        for attempt in range(1, 4):
            await submit_login_form(page, email, password)
            outcome = await wait_login_outcome(page, s, timeout=50)
            if outcome in ("2fa", "captcha", "authenticated", "error"):
                break
            if outcome == "login":
                continue
            break

        if outcome == "captcha":
            outcome = await hold_for_captcha_then_continue(page, s)

        if outcome in ("login", "transition", "timeout"):
            outcome = await hold_for_post_login(page, s, email, password)

        if outcome == "2fa":
            await do_2fa(page, s)
            outcome = "authenticated" if (await authenticated_visible(page)) else await classify_screen(page)

        if outcome == "authenticated" or await authenticated_visible(page):
            await post_login_cleanup(page)
            s.update(status="success", error=None, screen="authenticated")
        elif outcome == "error":
            s["status"] = "failed"
            if not s.get("error"):
                s["error"] = "Login was rejected."
        elif outcome == "2fa" or url_implies_2fa(page_url(page)) or await twofa_visible(page):
            s["status"] = "waiting_for_2fa_code" if s.get("2fa_card") == "code_entry" else "waiting_for_2fa_choice"
        else:
            s["status"] = s.get("status") if s.get("status") in ACTIVE_LOGIN_STATES else "logging_in"

        if keep_alive:
            while token in SESSIONS and s.get("status") != "closed":
                await asyncio.sleep(1)
    except Exception as e:
        logger.exception("Login failed")
        s.update(status="failed", error=str(e))
        if keep_alive:
            while token in SESSIONS and s.get("status") != "closed":
                await asyncio.sleep(1)
    finally:
        if not keep_alive or s.get("status") == "closed":
            for x in (context, browser):
                try:
                    if x:
                        await x.close()
                except Exception:
                    pass
            if pw:
                try:
                    await pw.stop()
                except Exception:
                    pass


def calculate_slider_offset_local(bg_bytes: bytes, slice_bytes: bytes) -> float:
    if _ocr:
        try:
            res = _ocr.slide_match(slice_bytes, bg_bytes, simple_target=True)
            if res and "target" in res:
                return float(res["target"][0])
        except Exception as e:
            logger.warning("[GEETEST] ddddocr match failed, falling back to OpenCV: %s", e)

    bg_img = cv2.imdecode(np.frombuffer(bg_bytes, np.uint8), cv2.IMREAD_COLOR)
    slice_img = cv2.imdecode(np.frombuffer(slice_bytes, np.uint8), cv2.IMREAD_COLOR)

    bg_gray = cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY)
    slice_gray = cv2.cvtColor(slice_img, cv2.COLOR_BGR2GRAY)

    bg_edges = cv2.Canny(bg_gray, 100, 200)
    slice_edges = cv2.Canny(slice_gray, 100, 200)

    res = cv2.matchTemplate(bg_edges, slice_edges, cv2.TM_CCOEFF_NORMED)
    _, _, _, max_loc = cv2.minMaxLoc(res)

    return float(max_loc[0])


async def auto_solve_and_submit(page: Page) -> bool:
    try:
        await page.wait_for_selector(".geetest_bg", timeout=7000)

        images = await page.evaluate('''() => {
            const bgEl = document.querySelector('.geetest_bg');
            const sliceEl = document.querySelector('.geetest_slice_bg');
            
            const extractUrl = (el) => {
                if (!el) return null;
                const style = window.getComputedStyle(el).backgroundImage;
                const match = style.match(/url\\(["']?(.*?)["']?\\)/);
                return match ? match[1] : null;
            };

            return {
                bg: extractUrl(bgEl),
                slice: extractUrl(sliceEl)
            };
        }''')

        bg_url = images.get("bg")
        slice_url = images.get("slice")

        if not bg_url or not slice_url:
            return False

        async with aiohttp.ClientSession() as http_session:
            async with http_session.get(bg_url) as resp_bg:
                bg_bytes = await resp_bg.read()
            async with http_session.get(slice_url) as resp_slice:
                slice_bytes = await resp_slice.read()

        target_x = calculate_slider_offset_local(bg_bytes, slice_bytes)

        slider_btn = page.locator(".geetest_btn").first
        box = await slider_btn.bounding_box()

        if not box:
            return False

        canvas_width = await page.evaluate('''() => {
            const el = document.querySelector('.geetest_window') || document.querySelector('.geetest_bg');
            return el ? el.getBoundingClientRect().width : 300;
        }''')

        scale_factor = canvas_width / 300.0
        start_x = box["x"] + box["width"] / 2
        start_y = box["y"] + box["height"] / 2
        final_distance = target_x * scale_factor

        await page.mouse.move(start_x, start_y)
        await page.mouse.down()

        steps = 30
        for i in range(1, steps + 1):
            progress = i / steps
            ease = 1 - pow(1 - progress, 3)
            current_x = start_x + (final_distance * ease)
            wobble_y = start_y + (1.2 if i % 2 == 0 else -1.2)
            await page.mouse.move(current_x, wobble_y)
            await asyncio.sleep(0.012)

        await page.mouse.up()
        await page.wait_for_timeout(1500)
        return True

    except Exception as e:
        logger.exception("[GEETEST] Local solver error: %s", e)
        return False


async def dismiss_overlays(page: Page) -> None:
    try:
        await page.add_style_tag(content="""
            /* Hide modal backdrops, promo wheels, campaign popups, and banners */
            .modal-backdrop, 
            .modal.show, 
            div[class*="popup"], 
            div[class*="overlay"], 
            div[class*="wheel"], 
            div[class*="campaign"],
            .bv-example-row { 
                display: none !important; 
                visibility: hidden !important; 
                pointer-events: none !important; 
            }
            body { 
                overflow: auto !important; 
            }
        """)
    except Exception as e:
        logger.debug("Overlay CSS injection skipped: %s", e)