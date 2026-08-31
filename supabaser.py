"""
supabaser.py (Compatibility Shim)
─────────────────────────────────
Legacy import path re-exporting from app.services.supabase_service.
"""

from app.services.supabase_service import (
    process_and_upload,
)

if __name__ == "__main__":
    process_and_upload()
