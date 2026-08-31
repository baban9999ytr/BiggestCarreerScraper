from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.export_security import ExportSecurityError, safe_export_path
from config import EXPORT_DIR, SESSIONS

router = APIRouter()


@router.get("/")
async def root():
    return {"status": "online"}


@router.get("/health")
async def health_check():
    return {"status": "healthy"}


from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
PUBLIC_INDEX = ROOT_DIR / "public" / "index.html"
FALLBACK_INDEX = ROOT_DIR / "index.html"


@router.get("/index", response_class=FileResponse)
async def index():
    if PUBLIC_INDEX.exists():
        return FileResponse(str(PUBLIC_INDEX))
    if FALLBACK_INDEX.exists():
        return FileResponse(str(FALLBACK_INDEX))
    raise HTTPException(status_code=404, detail="Index HTML not found.")


@router.get("/download-export/{token}/{filename}")
async def download_export(token: str, filename: str):
    """
    Serve a generated export file for an authenticated session.

    Security:
    - Token must map to a known session (any non-expired state).
    - Filename is validated against a strict allowlist before any filesystem access.
    - Path-traversal is prevented by both the regex and Path.resolve() confinement.
    - Only .json and .csv files inside the exports directory are served.
    """
    if token not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found.")

    try:
        file_path = safe_export_path(EXPORT_DIR, filename)
    except ExportSecurityError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    media_type = "application/json" if filename.endswith(".json") else "text/csv; charset=utf-8-sig"
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
