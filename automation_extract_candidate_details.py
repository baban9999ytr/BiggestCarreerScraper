from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from playwright.async_api import Page, async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("extract_candidate_details")

BASE_URL = "https://ats.kariyer.net"
CACHE_FILENAME = "extracted_cvs.json"
CACHE_TTL_DAYS = 180
CV_SCRAPE_DELAY_SECONDS = int(os.environ.get("CV_SCRAPE_DELAY_SECONDS", "30"))
CACHE_VERSION = 1

# /ozgecmis-detay/{jobId}/{candidateId}/{applicationId}
_DETAIL_URL_RE = re.compile(
    r"/ozgecmis-detay/(\d+)/(\d+)/(\d+)",
    re.IGNORECASE,
)

_EXTRACT_CV_JS = r"""
() => {
    const clean = (el) => (el?.textContent || el?.innerText || '').replace(/\s+/g, ' ').trim();
    const uniq = (arr) => [...new Set((arr || []).map((x) => String(x || '').trim()).filter(Boolean))];

    const nameEl = document.querySelector('.resume-candidate-card .name, .personal-information h1 b, h1 .name, .fullname');
    const nameText = clean(nameEl);

    let full_name = nameText;
    let age = "";
    const ageEl = document.querySelector('.resume-candidate-card .age, .personal-information .age');
    if (ageEl) {
        age = clean(ageEl).replace(/^,/, '').trim();
        if (nameEl) {
            const clone = nameEl.cloneNode(true);
            clone.querySelectorAll('.age').forEach(n => n.remove());
            full_name = clean(clone).replace(/,+$/, '').trim();
        }
    } else if (full_name) {
        const m = full_name.match(/^(.*?),?\s*(\d{1,2})\s*$/);
        if (m) {
            full_name = m[1].replace(/,+$/, '').trim();
            age = m[2];
        } else {
            full_name = full_name.replace(/,+$/, '').trim();
        }
    }

    const title = clean(document.querySelector('.resume-candidate-card .lg.font-weight-bold, .resume-candidate-card .title'));
    const location = clean(document.querySelector('.resume-candidate-card .location, #shortAddress'));
    const avatar_url = document.querySelector('.resume-candidate-card img, .personal-information img')?.getAttribute('src') || "";
    const open_to_work = !!document.querySelector('.opentowork-badge, .opentowork-wrapper, img[src*="open_to_work"]');

    const birth_date = clean(document.querySelector('#birthDate'));
    const short_address = clean(document.querySelector('#shortAddress'));
    const gender = clean(document.querySelector('#sex'));
    const nationality = clean(document.querySelector('#nationality'));

    const emails = [...document.querySelectorAll('.contact-information a[href^="mailto:"], a[href^="mailto:"]')]
        .map(a => (a.getAttribute('href') || '').replace('mailto:', '').trim())
        .filter(Boolean);

    const phones = [...document.querySelectorAll('.contact-information a[href^="tel:"], a[href^="tel:"]')]
        .map(a => (a.getAttribute('href') || '').replace('tel:', '').trim())
        .filter(Boolean);

    const cover_letter = clean(document.querySelector('.cover-letter-information .card-body, .cover-letter, #coverLetter'));

    const experiences = [...document.querySelectorAll('.work-information .list-content-wrapper')].map(exp => {
        const titleEl = exp.querySelector('.content .bold.md, .bold.md');
        const companyEl = titleEl?.querySelector('small.xs') || exp.querySelector('small.xs, .employer');
        const locEl = titleEl?.querySelector('small.bold') || exp.querySelector('small.bold');

        let job_title = clean(titleEl);
        if (companyEl) job_title = job_title.replace(clean(companyEl), '');
        if (locEl) job_title = job_title.replace(clean(locEl), '');

        const durationEl = exp.querySelector('.xs.col-5, .duration, .year');
        const sectors = [...exp.querySelectorAll('.summary-info-item')].map(item => {
            return `${clean(item.querySelector('.summary-title'))} ${clean(item.querySelector('.summary-label'))}`.trim();
        }).filter(Boolean);

        return {
            job_title: job_title.replace(/\s+/g, ' ').trim(),
            company: clean(companyEl),
            location: clean(locEl).replace(/^\//, '').trim(),
            duration_text: clean(durationEl),
            details: sectors.join(' | ')
        };
    });

    const education = [...document.querySelectorAll('.education-information .education-wrapper')].map(edu => ({
        school_name: clean(edu.querySelector('.name')),
        year_range: clean(edu.querySelector('.year')),
        faculty_or_type: clean(edu.querySelector('.f-name, .f-major')),
        department: clean(edu.querySelector('.f-sub'))
    }));

    const screening_questions = [...document.querySelectorAll('#collapse0 .other-applicant, .other-applicant')].map(item => ({
        question: clean(item.querySelector('.xs.bold')),
        answer: clean(item.querySelector('.sm'))
    })).filter(q => q.question);

    const kvkk_records = [...document.querySelectorAll('.kvkk-wrapper .applicant-information-consent')].map(consent => clean(consent)).filter(Boolean);

    const skills = uniq([...document.querySelectorAll('.skill-information .skill, .skills .tag, .keyword-item')].map(clean));
    const languages = [...document.querySelectorAll('.language-information .language-wrapper, .languages .list-content-wrapper')].map(row => ({
        language: clean(row.querySelector('.name, .bold, .language')),
        level: clean(row.querySelector('.level, .xs, .label'))
    })).filter(x => x.language);

    return {
        full_name,
        age,
        current_title: title,
        location,
        avatar_url,
        open_to_work,
        personal_info: {
            birth_date,
            address: short_address,
            gender,
            nationality
        },
        contact_info: {
            emails: uniq(emails),
            phones: uniq(phones)
        },
        cover_letter,
        experiences,
        education,
        skills,
        languages,
        screening_questions,
        kvkk_records
    };
}
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def parse_iso(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_detail_ids(detail_url: str) -> Dict[str, str]:
    """Parse /ozgecmis-detay/{jobId}/{candidateId}/{applicationId}."""
    if not detail_url:
        return {"job_id": "", "candidate_id": "", "application_id": ""}
    m = _DETAIL_URL_RE.search(detail_url)
    if not m:
        return {"job_id": "", "candidate_id": "", "application_id": ""}
    return {
        "job_id": m.group(1),
        "candidate_id": m.group(2),
        "application_id": m.group(3),
    }


def job_cache_key(job: Dict[str, Any], fallback_job_id: str = "") -> str:
    job_id = str(job.get("job_id") or fallback_job_id or "").strip()
    if job_id:
        return job_id
    ref = str(job.get("reference_number") or job.get("referans_no") or "").strip()
    if ref:
        return ref
    title = str(job.get("title") or job.get("ilan_basligi") or "").strip()
    return title or "unknown-job"


def empty_store() -> Dict[str, Any]:
    return {
        "version": CACHE_VERSION,
        "cache_ttl_days": CACHE_TTL_DAYS,
        "updated_at": iso(utcnow()),
        "jobs": {},
        "cvs": {},
    }


def load_cv_store(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return empty_store()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Could not read %s (%s); starting a fresh cache.", path, e)
        return empty_store()
    if not isinstance(data, dict):
        return empty_store()
    data.setdefault("version", CACHE_VERSION)
    data.setdefault("cache_ttl_days", CACHE_TTL_DAYS)
    data.setdefault("jobs", {})
    data.setdefault("cvs", {})
    return data


def save_cv_store(path: Path, store: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    store["updated_at"] = iso(utcnow())
    store["version"] = CACHE_VERSION
    store["cache_ttl_days"] = store.get("cache_ttl_days") or CACHE_TTL_DAYS
    fd, tmp_name = tempfile.mkstemp(prefix="extracted_cvs.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(store, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def cv_is_fresh(record: Optional[Dict[str, Any]], now: Optional[datetime] = None, ttl_days: int = CACHE_TTL_DAYS) -> bool:
    if not record or not isinstance(record, dict):
        return False
    if record.get("error") and not record.get("cv"):
        return False
    payload = record.get("cv") or record
    if payload.get("error") and not payload.get("full_name"):
        return False
    extracted = parse_iso(record.get("extracted_at"))
    expires = parse_iso(record.get("expires_at"))
    now = now or utcnow()
    if expires:
        return expires > now
    if extracted:
        return extracted + timedelta(days=ttl_days) > now
    return False


def listings_view(store: Dict[str, Any]) -> Dict[str, Any]:
    """Nested view: { jobKey: { last_extracted_at, job meta, cvs: [...] } }."""
    cvs = store.get("cvs") or {}
    out: Dict[str, Any] = {}
    for key, job in (store.get("jobs") or {}).items():
        attached = []
        for app in job.get("applications") or []:
            cand_id = str(app.get("candidate_id") or "")
            cv_rec = cvs.get(cand_id) or {}
            attached.append(
                {
                    "candidate_id": cand_id,
                    "application_id": app.get("application_id") or "",
                    "detail_url": app.get("detail_url") or "",
                    "card_name": app.get("card_name") or "",
                    "card_title": app.get("card_title") or "",
                    "extracted_at": cv_rec.get("extracted_at"),
                    "expires_at": cv_rec.get("expires_at"),
                    "from_cache": True,
                    "cv": cv_rec.get("cv"),
                }
            )
        out[key] = {
            "job_id": job.get("job_id") or key,
            "reference_number": job.get("reference_number") or "",
            "title": job.get("title") or "",
            "company": job.get("company") or "",
            "last_extracted_at": job.get("last_extracted_at"),
            "cv_count": len(attached),
            "cvs": attached,
        }
    return out


async def reveal_contact_information(page: Page) -> None:
    try:
        reveal_btn = page.locator(
            "a.remove-blur:has-text('İletişim Bilgilerini Görüntüle'), "
            "a.remove-blur:has-text('İletİŞİm Bİlgİlerİnİ Görüntüle'), "
            "a.remove-blur"
        ).first
        if await reveal_btn.is_visible(timeout=3000):
            logger.info("Un-blurring candidate contact information...")
            await reveal_btn.click(force=True)
            try:
                await page.wait_for_selector(
                    ".contact-information a[href^='mailto:'], .contact-information a[href^='tel:']",
                    timeout=4000,
                )
            except Exception:
                await page.wait_for_timeout(1500)
    except Exception as e:
        logger.debug("Contact un-blur button not triggered or already visible: %s", e)


async def scrape_candidate_cv(page: Page, detail_url: str) -> Dict[str, Any]:
    target_url = f"{BASE_URL}{detail_url}" if str(detail_url).startswith("/") else detail_url
    logger.info("Scraping Candidate CV: %s", target_url)

    try:
        await page.goto(target_url, wait_until="domcontentloaded", timeout=40000)

        try:
            await page.wait_for_selector("#app:not(.loading)", timeout=15000)
        except Exception:
            logger.warning("App element still has 'loading' class, proceeding with fallback checks...")

        await page.wait_for_selector(
            ".personal-information h1 b, .work-information, #birthDate, .resume-candidate-card",
            timeout=15000,
            state="attached",
        )

        await reveal_contact_information(page)

        cv_data: Dict[str, Any] = {}
        for attempt in range(6):
            cv_data = await page.evaluate(_EXTRACT_CV_JS)

            has_name = bool(cv_data.get("full_name") and str(cv_data.get("full_name")).strip())
            has_exp = bool(cv_data.get("experiences"))
            has_edu = bool(cv_data.get("education"))

            if has_name or has_exp or has_edu:
                break

            logger.warning("CV content still loading (skeleton) on attempt %d/6...", attempt + 1)
            await page.wait_for_timeout(800)

        cv_data["source_url"] = target_url
        cv_data["scraped_at"] = iso(utcnow())
        return cv_data

    except Exception as err:
        logger.error("Failed to scrape CV at %s: %s", target_url, err)
        return {"source_url": target_url, "error": str(err), "scraped_at": iso(utcnow())}


async def _pace_after_live_scrape(delay_seconds: int) -> None:
    if delay_seconds <= 0:
        return
    logger.info("Waiting %ss before the next live CV request (server load guard)...", delay_seconds)
    await asyncio.sleep(delay_seconds)


def _ensure_job_entry(store: Dict[str, Any], job: Dict[str, Any], job_id: str) -> Dict[str, Any]:
    key = job_cache_key(job, job_id)
    jobs = store.setdefault("jobs", {})
    entry = jobs.get(key) or {}
    entry["job_id"] = job_id or entry.get("job_id") or key
    entry["reference_number"] = (
        job.get("reference_number") or job.get("referans_no") or entry.get("reference_number") or ""
    )
    entry["title"] = job.get("title") or job.get("ilan_basligi") or entry.get("title") or ""
    entry["company"] = job.get("company") or job.get("sirket_sayfasi") or entry.get("company") or ""
    entry.setdefault("applications", [])
    jobs[key] = entry
    return entry


def _upsert_application(job_entry: Dict[str, Any], app: Dict[str, Any]) -> None:
    apps: List[Dict[str, Any]] = job_entry.setdefault("applications", [])
    cand = app.get("candidate_id") or ""
    appl = app.get("application_id") or ""
    url = app.get("detail_url") or ""
    for existing in apps:
        if (appl and existing.get("application_id") == appl) or (
            cand and existing.get("candidate_id") == cand and existing.get("detail_url") == url
        ):
            existing.update({k: v for k, v in app.items() if v})
            return
    apps.append(app)


def _normalize_jobs_payload(jobs_data: Any) -> List[Dict[str, Any]]:
    if isinstance(jobs_data, list):
        return [j for j in jobs_data if isinstance(j, dict)]
    if isinstance(jobs_data, dict):
        if isinstance(jobs_data.get("jobs"), list):
            return [j for j in jobs_data["jobs"] if isinstance(j, dict)]
        if isinstance(jobs_data.get("jobs"), dict) and "cvs" in jobs_data:
            return []
    return []


async def extract_cvs_for_jobs(
    page: Page,
    jobs: Iterable[Dict[str, Any]],
    cache_path: Path | str = CACHE_FILENAME,
    delay_seconds: int = CV_SCRAPE_DELAY_SECONDS,
    force_refresh: bool = False,
    ttl_days: int = CACHE_TTL_DAYS,
) -> Dict[str, Any]:
    """
    Walk job listings, scrape each new CV at most once per `ttl_days` (default 6 months).

    Live ATS hits are paced at `delay_seconds` (default 30) so the server is not overloaded.
    Cache hits (same candidate on another job, or a second run by the same company)
    skip both the network request and the delay.
    """
    cache_path = Path(cache_path)
    store = load_cv_store(cache_path)
    now = utcnow()
    live_scrapes = 0
    cache_hits = 0
    skipped_no_url = 0

    job_list = list(jobs)
    logger.info(
        "CV extraction starting (%d jobs). Cache=%s ttl=%dd delay=%ss force=%s",
        len(job_list),
        cache_path,
        ttl_days,
        delay_seconds,
        force_refresh,
    )

    for job in job_list:
        candidates = job.get("candidates") or []
        sample_url = ""
        for cand in candidates:
            if cand.get("detail_url"):
                sample_url = cand["detail_url"]
                break
        parsed_job_id = parse_detail_ids(sample_url)["job_id"] or str(job.get("job_id") or "")
        job_entry = _ensure_job_entry(store, job, parsed_job_id)
        logger.info(
            "Job '%s' (id=%s ref=%s) — %d applicants",
            job_entry.get("title") or "?",
            job_entry.get("job_id"),
            job_entry.get("reference_number"),
            len(candidates),
        )

        for candidate in candidates:
            detail_url = candidate.get("detail_url") or ""
            if not detail_url:
                skipped_no_url += 1
                continue

            ids = parse_detail_ids(detail_url)
            candidate_id = ids["candidate_id"]
            if not candidate_id:
                candidate_id = re.sub(r"[^0-9a-zA-Z]+", "_", detail_url)[:80]

            _upsert_application(
                job_entry,
                {
                    "candidate_id": candidate_id,
                    "application_id": ids["application_id"],
                    "job_id": ids["job_id"] or job_entry.get("job_id"),
                    "detail_url": detail_url,
                    "card_name": candidate.get("name") or "",
                    "card_title": candidate.get("title") or "",
                    "linked_at": iso(now),
                },
            )

            cached = (store.get("cvs") or {}).get(candidate_id)
            if not force_refresh and cv_is_fresh(cached, now=now, ttl_days=ttl_days):
                cache_hits += 1
                logger.info(
                    "Cache hit for candidate %s (%s) — extracted %s, skip live scrape",
                    candidate_id,
                    candidate.get("name") or "?",
                    cached.get("extracted_at"),
                )
                continue

            cv_payload = await scrape_candidate_cv(page, detail_url)
            live_scrapes += 1
            extracted_at = utcnow()
            ok = not cv_payload.get("error")
            if ok or not cv_is_fresh(cached, now=extracted_at, ttl_days=ttl_days):
                store.setdefault("cvs", {})[candidate_id] = {
                    "candidate_id": candidate_id,
                    "extracted_at": iso(extracted_at),
                    "expires_at": iso(extracted_at + timedelta(days=ttl_days)),
                    "source_url": cv_payload.get("source_url") or detail_url,
                    "cv": cv_payload,
                }
            job_entry["last_extracted_at"] = iso(extracted_at)
            save_cv_store(cache_path, store)
            await _pace_after_live_scrape(delay_seconds)

        job_entry["last_extracted_at"] = iso(utcnow())
        save_cv_store(cache_path, store)

    logger.info(
        "CV extraction finished. live_scrapes=%d cache_hits=%d skipped_no_url=%d file=%s",
        live_scrapes,
        cache_hits,
        skipped_no_url,
        cache_path,
    )
    store["_run_stats"] = {
        "live_scrapes": live_scrapes,
        "cache_hits": cache_hits,
        "skipped_no_url": skipped_no_url,
    }
    return store


def find_jobs_file_by_token(token: str, search_dir: str = ".") -> Optional[Path]:
    path = Path(search_dir)
    pattern = f"kariyer_jobs_{token}_*.json"
    matches = sorted(path.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    if not matches:
        exact_match = path / f"kariyer_jobs_{token}.json"
        if exact_match.exists():
            return exact_match
        return None

    return matches[0]


async def process_candidate_details_for_token(
    token: str,
    page: Page,
    search_dir: str = ".",
    output_dir: str = ".",
    cache_path: Optional[Path | str] = None,
    delay_seconds: int = CV_SCRAPE_DELAY_SECONDS,
    force_refresh: bool = False,
) -> Optional[Path]:
    jobs_file = find_jobs_file_by_token(token, search_dir)
    if not jobs_file:
        logger.error("No JSON file found for token: %s", token)
        return None

    logger.info("Found job file: %s", jobs_file)
    with open(jobs_file, "r", encoding="utf-8") as f:
        jobs_data = json.load(f)

    jobs = _normalize_jobs_payload(jobs_data)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_file = Path(cache_path) if cache_path else out_dir / CACHE_FILENAME

    store = await extract_cvs_for_jobs(
        page,
        jobs,
        cache_path=cache_file,
        delay_seconds=delay_seconds,
        force_refresh=force_refresh,
    )

    listings = listings_view(store)
    listings_path = out_dir / f"kariyer_candidate_details_{token}.json"
    with listings_path.open("w", encoding="utf-8") as f:
        json.dump(listings, f, ensure_ascii=False, indent=2)
        f.write("\n")

    logger.info(
        "Wrote listings view to %s and canonical cache to %s",
        listings_path,
        cache_file,
    )
    return cache_file


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Extract Kariyer.net ATS CVs with a 6-month cache.")
    parser.add_argument("token", nargs="?", default="", help="jobs file token (kariyer_jobs_{token}_*.json)")
    parser.add_argument("--jobs-json", dest="jobs_json", default="", help="explicit jobs JSON path")
    parser.add_argument("--cache", dest="cache", default=CACHE_FILENAME, help="extracted_cvs.json path")
    parser.add_argument("--delay", dest="delay", type=int, default=CV_SCRAPE_DELAY_SECONDS)
    parser.add_argument("--force", dest="force", action="store_true", help="ignore cache and re-scrape")
    args = parser.parse_args()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        try:
            if args.jobs_json:
                with open(args.jobs_json, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                jobs = _normalize_jobs_payload(payload)
                store = await extract_cvs_for_jobs(
                    page,
                    jobs,
                    cache_path=args.cache,
                    delay_seconds=args.delay,
                    force_refresh=args.force,
                )
                print(f"Extraction complete. Cache: {args.cache} stats={store.get('_run_stats')}")
            else:
                result_file = await process_candidate_details_for_token(
                    args.token,
                    page,
                    cache_path=args.cache,
                    delay_seconds=args.delay,
                    force_refresh=args.force,
                )
                if result_file:
                    print(f"Extraction complete! Results written to {result_file}")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())