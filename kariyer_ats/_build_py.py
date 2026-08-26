from pathlib import Path

js = Path("/workspace/kariyer_ats/extract_wizard.js").read_text(encoding="utf-8")

header = r'''from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import aiohttp
from playwright.async_api import Locator, Page

logger = logging.getLogger("automation_process_jobs")

_EXTRACT_WIZARD_JS = r"""
'''

footer = r'''
"""


def _wizard_js() -> str:
    src = _EXTRACT_WIZARD_JS.strip()
    if src.startswith("()"):
        return f"({src})()"
    return src


def _has_wizard_signal(data: Dict[str, Any]) -> bool:
    for key in (
        "pozisyon",
        "ilan_basligi",
        "departman",
        "lokasyon",
        "yetenekler",
        "ilan_aciklamasi",
        "calistigi_pozisyonlar",
        "sirket_sayfasi",
    ):
        val = data.get(key)
        if isinstance(val, list) and any(str(x).strip() for x in val):
            return True
        if isinstance(val, str) and val.strip() and val.strip() != "[]":
            return True
    return False


def _public_wizard(data: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(data or {})
    data.pop("_vue_model_found", None)
    return data


_OVERLAY_KILLER_JS = r"""
(() => {
    if (window.__overlayKillerInstalled) return;
    window.__overlayKillerInstalled = true;
    const KNOWN_SELECTORS = [
        '.modal-backdrop', '.modal.show', '.mfp-bg', '.mfp-wrap',
        '[class*="wis-mfp-content"]', '#wis-lightbox',
        '[class*="wis-offer-counter-reminder"]', '[class*="wis-offer-counter-modal"]',
        '[class*="wis-offer"]', '[class*="popup"]', '[class*="overlay"]',
        '[class*="wheel"]', '[class*="campaign"]', '[class*="spin"]',
        '.bv-example-row'
    ];
    const isSiteChrome = (el) => {
        return el.closest(
            '#main_sidebar_menu, .sidebarnew, #dashboard, .sub-header, ' +
            '#nav_collapse_new, .sidebarmenu-wrapper'
        ) !== null;
    };
    const looksLikeFullscreenOverlay = (el) => {
        if (isSiteChrome(el)) return false;
        let st;
        try { st = getComputedStyle(el); } catch (e) { return false; }
        if (!st || !['fixed', 'sticky'].includes(st.position)) return false;
        const z = parseInt(st.zIndex, 10);
        if (!z || z < 999) return false;
        const r = el.getBoundingClientRect();
        const vw = window.innerWidth, vh = window.innerHeight;
        if (r.width < vw * 0.3 || r.height < vh * 0.3) return false;
        return true;
    };
    const kill = (el) => {
        try {
            el.style.setProperty('display', 'none', 'important');
            el.style.setProperty('visibility', 'hidden', 'important');
            el.style.setProperty('pointer-events', 'none', 'important');
        } catch (e) {}
    };
    const sweep = () => {
        try {
            KNOWN_SELECTORS.forEach((sel) => {
                document.querySelectorAll(sel).forEach((el) => {
                    if (!isSiteChrome(el)) kill(el);
                });
            });
            document.querySelectorAll('body > *, #app > *').forEach((el) => {
                if (looksLikeFullscreenOverlay(el)) kill(el);
            });
        } catch (e) {}
        try {
            document.documentElement.style.setProperty('overflow', 'auto', 'important');
            if (document.body) {
                document.body.style.setProperty('overflow', 'auto', 'important');
                document.body.classList.remove('modal-open');
            }
        } catch (e) {}
    };
    sweep();
    const mo = new MutationObserver(() => sweep());
    const start = () => mo.observe(document.documentElement, { childList: true, subtree: true });
    if (document.documentElement) {
        start();
    } else {
        document.addEventListener('DOMContentLoaded', start, { once: true });
    }
    setInterval(sweep, 1000);
})();
"""


async def install_overlay_killer(context: Any) -> None:
    try:
        await context.add_init_script(_OVERLAY_KILLER_JS)
        logger.info("Overlay killer installed on browser context.")
    except Exception as e:
        logger.warning("Failed to install overlay killer: %s", e)


async def _wait_for_selector_resilient(page: Page, selector: str, timeout: float = 25.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            if await page.locator(selector).first.is_visible(timeout=500):
                return True
        except Exception:
            pass
        await dismiss_overlays(page)
        await clear_blocking_popups(page)
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        await page.wait_for_timeout(700)
    try:
        return await page.locator(selector).first.is_visible(timeout=500)
    except Exception:
        return False


_WIZARD_READY_SELECTOR = (
    "#jobPosition, #jobPositionFormGroup, .multiselect__single, "
    ".multiselect__tag, .trumbowyg-editor, input#titleFormInput"
)


async def hydrate_wizard_steps(page: Page) -> None:
    """Force every wizard step into the DOM, then wait for real fields.

    Vue `mode="out-in"` often keeps only the active step mounted. Clicking
    the stepper (including disabled items, force=True) is what makes later
    panels exist for extraction. Waiting on `.new-jobpage` alone is wrong:
    that shell is present during the skeleton loader.
    """
    await dismiss_overlays(page)
    await clear_blocking_popups(page)
    ok = await _wait_for_selector_resilient(page, _WIZARD_READY_SELECTOR, timeout=20.0)
    if not ok:
        logger.warning("Wizard fields not visible yet; will still try stepper + extract.")
    try:
        links = page.locator("#toc-stepper-ul a, .vertical-stepper a, .stepper-wrapper li a")
        count = await links.count()
        for i in range(count):
            try:
                await links.nth(i).click(force=True, timeout=1500)
                await page.wait_for_timeout(400)
                await dismiss_overlays(page)
            except Exception:
                continue
        if count:
            try:
                await links.nth(0).click(force=True, timeout=1500)
                await page.wait_for_timeout(250)
            except Exception:
                pass
    except Exception as e:
        logger.debug("Stepper hydration skipped: %s", e)


async def extract_wizard_job_details(page: Page) -> Dict[str, Any]:
    await hydrate_wizard_steps(page)
    data: Dict[str, Any] = {}
    for attempt in range(8):
        try:
            data = await page.evaluate(_wizard_js())
        except Exception as e:
            logger.warning("Wizard evaluate failed (attempt %d): %s", attempt + 1, e)
            data = {}
        if isinstance(data, dict) and _has_wizard_signal(data):
            return _public_wizard(data)
        await dismiss_overlays(page)
        await page.wait_for_timeout(450)
        if attempt in (2, 5):
            await hydrate_wizard_steps(page)
    logger.warning("Wizard extract finished without a strong signal; returning last payload.")
    return _public_wizard(data if isinstance(data, dict) else {})


async def extract_candidate_cv_detail(page: Page) -> Dict[str, Any]:
    return await page.evaluate(
        r"""() => {
            const t = el => (el?.textContent || el?.innerText || '').replace(/\s+/g, ' ').trim();
            return {
                extracted_at: new Date().toISOString(),
                candidate_name: t(document.querySelector('.resume-candidate-card .name')) || "",
                candidate_title: t(document.querySelector('.resume-candidate-card .lg.font-weight-bold')) || "",
                location: t(document.querySelector('#shortAddress')) || "",
                birth_date: t(document.querySelector('#birthDate')) || "",
                gender: t(document.querySelector('#sex')) || "",
                experiences: [...document.querySelectorAll('.work-information .list-content-wrapper')].map(exp => ({
                    title: t(exp.querySelector('.bold.md')),
                    duration: t(exp.querySelector('.xs.col-5')),
                    sector: t(exp.querySelector('.summary-info-item:nth-child(1) .summary-label')),
                })),
                education: [...document.querySelectorAll('.education-information .education-wrapper')].map(edu => ({
                    school: t(edu.querySelector('.name')),
                    degree: t(edu.querySelector('.f-major')),
                    years: t(edu.querySelector('.year')),
                }))
            };
        }"""
    )


async def extract_job_card_metadata(card_locator: Locator) -> Dict[str, Any]:
    try:
        title_el = card_locator.locator("h2.new-job-title a").first
        title = await title_el.text_content() if await title_el.count() else ""
        href = await title_el.get_attribute("href") if await title_el.count() else ""
        ref_el = card_locator.locator(".top_bar-ref").first
        ref_no = await ref_el.text_content() if await ref_el.count() else ""
        company_el = card_locator.locator(".job-card_profile-name").first
        company = await company_el.text_content() if await company_el.count() else ""
        apps_el = (
            card_locator.locator(".count-item .count-label:has-text('Başvuru')")
            .locator("..")
            .locator("a span")
            .first
        )
        apps_count = await apps_el.text_content() if await apps_el.count() else "0"
        return {
            "title": (title or "").strip() or "",
            "href": href or "",
            "reference_number": (ref_no or "").strip() or "",
            "company": (company or "").strip() or "",
            "applications_count": (apps_count or "").strip() or "0",
        }
    except Exception as e:
        logger.warning("Error parsing single job card: %s", e)
        return {}


async def clear_blocking_popups(page: Page) -> None:
    click_targets = [
        ".wis-offer-counter-reminder-0000-content",
        "div[class*='wis-offer-counter-reminder']",
        "[class*='wis-mfp-close']",
        "button.mfp-close",
        "#wis-lightbox button",
        "button.close",
        ".modal-header button",
        "[aria-label='Close']",
        ".btn-close",
        "button:has-text('Kapat')",
        "button:has-text('Vazgeç')",
        ".popup-close-btn",
    ]
    for selector in click_targets:
        try:
            target = page.locator(selector).first
            if await target.is_visible(timeout=500):
                logger.info("Triggered auto-click on target: %s", selector)
                await target.click(force=True)
                await page.wait_for_timeout(300)
        except Exception:
            pass


async def dismiss_overlays(page: Page) -> None:
    try:
        await page.add_style_tag(
            content="""
            .modal-backdrop,
            .modal.show,
            .mfp-bg,
            .mfp-wrap,
            [class*="wis-mfp-content"],
            #wis-lightbox,
            div[class*="wis-offer-counter-reminder"],
            div[class*="wis-offer-counter-modal"],
            div[class*="wis-offer"],
            div[class*="popup"],
            div[class*="overlay"],
            div[class*="wheel"],
            div[class*="campaign"],
            .bv-example-row {
                display: none !important;
                visibility: hidden !important;
                pointer-events: none !important;
            }
            body, html { overflow: auto !important; }
        """
        )
    except Exception as e:
        logger.debug("Overlay CSS injection skipped: %s", e)


async def is_user_logged_in(page: Page) -> bool:
    logged_in_selectors = [
        "#user-info",
        "#dashboard-job-list",
        "#dashboard-articles-list",
        ".page-view",
    ]
    for selector in logged_in_selectors:
        if await page.locator(selector).count() > 0:
            return True
    return False


async def _navigate_to_listings(page: Page) -> None:
    await page.goto("https://ats.kariyer.net/ilanlarim/yayindakiler", wait_until="domcontentloaded")
    await dismiss_overlays(page)
    await clear_blocking_popups(page)
    ok = await _wait_for_selector_resilient(page, ".wide-card.job-card", timeout=25.0)
    if not ok:
        logger.warning(
            "Job cards did not become visible after overlay cleanup on /ilanlarim/yayindakiler; "
            "continuing anyway, downstream calls will report if the page is truly empty."
        )
    await page.wait_for_timeout(1000)


_CANDIDATE_LIST_JS = r"""() => {
    const t = el => (el?.textContent || '').replace(/\s+/g, ' ').trim();
    return [...document.querySelectorAll('.resume-card')].map(c => {
        const name = t(c.querySelector('.fullname')).replace(/,+$/, '');
        return {
            name,
            title: t(c.querySelector('.card-width-limiter .font-weight-bold')),
            detail_url: c.closest('a')?.getAttribute('href') || ''
        };
    });
}"""


async def _extract_candidates_from(target: Page) -> List[Dict[str, Any]]:
    try:
        await target.wait_for_selector(".resume-card, #job-list-page", timeout=12000)
    except Exception:
        pass
    await dismiss_overlays(target)
    await clear_blocking_popups(target)
    try:
        return await target.evaluate(_CANDIDATE_LIST_JS)
    except Exception as e:
        logger.warning("Candidate list extract failed: %s", e)
        return []


async def process_jobs_task(page: Page, limit: int = 100) -> List[Dict[str, Any]]:
    logger.info("Starting Multi-Step Pipeline process_jobs_task (limit=%d)...", limit)
    jobs_processed: List[Dict[str, Any]] = []
    try:
        await dismiss_overlays(page)
        await clear_blocking_popups(page)
        if await is_user_logged_in(page):
            logger.info("User dashboard detected. Post-login and 2FA state confirmed.")
        if await page.locator("#resume-left-tabs").count() > 0:
            logger.info("Detected CV detail page. Extracting CV details...")
            details = await extract_candidate_cv_detail(page)
            return [details]
        if await page.locator(".new-jobpage").count() > 0 or await page.locator("#jobPositionFormGroup").count() > 0:
            logger.info("Detected Job Wizard. Extracting full job details...")
            job_data = await extract_wizard_job_details(page)
            return [job_data]
        if "/ilanlarim/yayindakiler" not in page.url.lower():
            logger.info("Navigating to active job listings...")
            await _navigate_to_listings(page)
        card_selector = ".wide-card.job-card"

        while len(jobs_processed) < limit:
            if not await _wait_for_selector_resilient(page, card_selector, timeout=20.0):
                logger.warning("No job cards found on page after overlay cleanup. Exiting loop.")
                break
            count = await page.locator(card_selector).count()
            logger.info("Found %d published job cards on current page.", count)
            for i in range(count):
                if len(jobs_processed) >= limit:
                    break
                logger.info("Processing job card %d/%d on current page...", i + 1, count)
                card = page.locator(card_selector).nth(i)
                job_record = await extract_job_card_metadata(card)
                job_record["candidates"] = []
                edit_btn = card.locator("button[name='editAdd']").first
                if await edit_btn.is_visible():
                    logger.info("Clicking 'İlanı Düzenle' for job %d...", i + 1)
                    try:
                        async with page.expect_popup(timeout=3000) as popup_info:
                            await edit_btn.click(force=True)
                        target_page = await popup_info.value
                        await target_page.wait_for_load_state("domcontentloaded")
                        wizard_data = await extract_wizard_job_details(target_page)
                        job_record.update(wizard_data)
                        await target_page.close()
                    except Exception:
                        ready = await _wait_for_selector_resilient(page, _WIZARD_READY_SELECTOR, timeout=12.0)
                        if not ready:
                            try:
                                await page.wait_for_selector("#jobPositionFormGroup, .new-jobpage", timeout=8000)
                            except Exception:
                                pass
                        wizard_data = await extract_wizard_job_details(page)
                        job_record.update(wizard_data)
                        await _navigate_to_listings(page)
                card = page.locator(card_selector).nth(i)
                toggle_btn = card.locator(".dropdown-toggle-split").first
                if await toggle_btn.is_visible():
                    logger.info("Opening dropdown & clicking 'Başvuruları Gör' for job %d...", i + 1)
                    await toggle_btn.click(force=True)
                    await page.wait_for_timeout(300)
                    see_apps_btn = card.locator("button[name='displayApplications']").first
                    if await see_apps_btn.is_visible():
                        try:
                            async with page.expect_popup(timeout=3000) as popup_info:
                                await see_apps_btn.click(force=True)
                            target_page = await popup_info.value
                            await target_page.wait_for_load_state("domcontentloaded")
                            job_record["candidates"] = await _extract_candidates_from(target_page)
                            await target_page.close()
                        except Exception:
                            job_record["candidates"] = await _extract_candidates_from(page)
                            await _navigate_to_listings(page)
                jobs_processed.append(job_record)
            if len(jobs_processed) >= limit:
                break
            next_btn_container = page.locator("li.page-item", has_text="Sonraki").first
            class_attr = await next_btn_container.get_attribute("class") or ""
            if "disabled" in class_attr:
                logger.info("Reached the last page. Pagination complete.")
                break
            next_link = next_btn_container.locator("a.page-link")
            if await next_link.is_visible():
                logger.info("Moving to next page...")
                await next_link.click(force=True)
                await page.wait_for_timeout(3000)
            else:
                break
    except Exception as err:
        logger.exception("Error during job processing: %s", err)
        raise err
    logger.info("Job processing finished. Total extracted: %d", len(jobs_processed))
    return jobs_processed


async def extract_and_send_jobs(page: Page, target_api_url: str, limit: int = 100) -> Dict[str, Any]:
    logger.info("Starting job extraction task...")
    extracted_jobs = await process_jobs_task(page, limit=limit)
    payload = {
        "status": "success",
        "total_jobs": len(extracted_jobs),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "jobs": extracted_jobs,
    }
    logger.info("Sending extracted payload to %s...", target_api_url)
    async with aiohttp.ClientSession() as http_session:
        try:
            async with http_session.post(target_api_url, json=payload, timeout=30) as resp:
                status_code = resp.status
                response_text = await resp.text()
                logger.info("POST request returned status: %d", status_code)
                return {
                    "http_status": status_code,
                    "response": response_text,
                    "payload": payload,
                }
        except Exception as e:
            logger.exception("Failed to send POST request: %s", e)
            return {"error": str(e), "payload": payload}


async def extract_current_job(page: Page) -> Dict[str, Any]:
    return await extract_wizard_job_details(page)
'''

out = Path("/workspace/automation_process_jobs.py")
out.write_text(header + js + footer, encoding="utf-8")
print("wrote", out, "bytes", out.stat().st_size)