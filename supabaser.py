"""
supabaser.py (Compatibility Shim)
─────────────────────────────────
Legacy import path re-exporting from app.services.supabase_service.
"""

from app.services.supabase_service import (
    SCHEMA_NAME,
    TABLE_NAME,
    TARGET_KEYS,
    filter_and_enrich_data,
    is_logging_enabled,
    load_processed_files,
    process_and_upload,
    save_processed_files,
)

if __name__ == "__main__":
    process_and_upload()
