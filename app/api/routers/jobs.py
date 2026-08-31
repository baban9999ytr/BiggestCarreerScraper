import asyncio
import csv
import json
import logging
import os
import uuid
from typing import Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.api.dependencies import require_session
from app.core.config import settings
from app.core.url_validation import SSRFError, validate_target_url
from app.models.schemas import ExportRequest, TokenOnly
from app.services.supabase_service import process_and_upload
from automation_extract_candidate_details import process_candidate_details_for_token
from automation_process_jobs import extract_and_send_jobs, process_jobs_task
from config import EXPORT_DIR, SESSIONS

logger = logging.getLogger("kariyer_api.jobs")
router = APIRouter()


class HandleJobsRequest(BaseModel):
    target_url: str = Field(
        ...,  # required — no insecure default that could be forgotten in production
        description="Destination HTTPS URL to receive the extracted job payload via POST.",
        min_length=10,
        max_length=2048,
    )
    limit: int = Field(
        default=10, ge=1, le=500, description="Maximum number of job listings to process."
    )


def write_exports(token: str, jobs: List[Dict]) -> Dict[str, str]:
    stem = f"kariyer_jobs_{token}_{uuid.uuid4().hex[:8]}"
    j, c = f"{stem}.json", f"{stem}.csv"
    with open(os.path.join(EXPORT_DIR, j), "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)

    if jobs:
        cols = list(jobs[0].keys())
    else:
        cols = []

    with open(os.path.join(EXPORT_DIR, c), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for x in jobs:
            w.writerow(
                {
                    k: json.dumps(x[k], ensure_ascii=False)
                    if isinstance(x.get(k), (list, dict))
                    else x.get(k, "")
                    for k in cols
                }
            )
    # Use the protected download route — do NOT expose a raw /exports/ static path
    return {
        "json": f"/download-export/{token}/{j}",
        "csv": f"/download-export/{token}/{c}",
    }


@router.post("/process-candidate-details")
async def process_candidate_details(p: TokenOnly, tasks: BackgroundTasks):
    s = await require_session(p.token)
    page = s.get("page") if s else None

    if not page or s.get("status") not in ("success", "authenticated"):
        raise HTTPException(400, "Session is not ready or authenticated.")

    if s.get("is_processing_candidate_details"):
        raise HTTPException(
            409, "A candidate details extraction task is already running for this session."
        )

    s["is_processing_candidate_details"] = True

    async def _candidate_runner():
        try:
            async with s["lock"]:
                out_path = await process_candidate_details_for_token(
                    token=p.token, page=page, search_dir=EXPORT_DIR, output_dir=EXPORT_DIR
                )

            if out_path:
                s["candidate_details_file"] = f"/exports/{out_path.name}"
                s["last_candidate_export_result"] = {
                    "status": "completed",
                    "export_url": f"/exports/{out_path.name}",
                }
            else:
                s["last_candidate_export_result"] = {
                    "status": "failed",
                    "error": "No job listings JSON found for this token.",
                }
        except Exception as e:
            logger.exception(
                "Background candidate details processing failed for token %s: %s", p.token, e
            )
            s["last_candidate_export_result"] = {"status": "failed", "error": str(e)}
        finally:
            s["is_processing_candidate_details"] = False

    tasks.add_task(_candidate_runner)

    return {
        "status": "processing",
        "token": p.token,
        "message": "Candidate CV details extraction started in background.",
    }


@router.get("/candidate-details-status/{token}")
async def candidate_details_status(token: str):
    s = await require_session(token)
    return {
        "token": token,
        "is_processing": s.get("is_processing_candidate_details", False),
        "result": s.get("last_candidate_export_result"),
    }


@router.post("/process-jobs")
async def process_jobs(p: ExportRequest, tasks: BackgroundTasks):
    s = await require_session(p.token)
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
                    filters=filter_payload,
                )

            exports = write_exports(p.token, jobs)
            s["jobs_exported"] = len(jobs)
            s["last_export_result"] = {
                "status": "completed",
                "count": len(jobs),
                "exports": exports,
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
        "message": f"Job processing started in background for limit={p.limit}, candidates_limit={p.max_candidates_per_job}.",
    }


@router.post("/trigger-supabaser")
async def trigger_supabaser(tasks: BackgroundTasks):
    tasks.add_task(asyncio.to_thread, process_and_upload)
    return {"status": "queued", "message": "Supabaser background processing task queued."}


@router.get("/export-status/{token}")
async def export_status(token: str):
    s = await require_session(token)
    return {
        "token": token,
        "is_processing": s.get("is_processing_jobs", False),
        "jobs_exported": s.get("jobs_exported", 0),
        "result": s.get("last_export_result"),
    }


@router.post("/handle-jobs/{token}")
async def handle_jobs_endpoint(
    token: str,
    req: HandleJobsRequest,
    background_tasks: BackgroundTasks,
):
    try:
        validated_url = validate_target_url(req.target_url)
    except SSRFError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    session_state = await require_session(token)
    page = session_state.get("page")

    if not page or session_state.get("status") not in ("success", "authenticated"):
        raise HTTPException(status_code=400, detail="Session not authenticated or page lost.")

    background_tasks.add_task(
        extract_and_send_jobs, token, page, validated_url, req.limit, session_state
    )

    return {
        "status": "accepted",
        "token": token,
        "message": f"Job extraction started in background. Results will be posted to {validated_url}.",
    }
