"""
supabaser.py (Compatibility Shim)
─────────────────────────────────
Legacy import path re-exporting from app.services.supabase_service.
"""
from app.services.supabase_service import (
    process_and_upload,
    is_logging_enabled,
    filter_and_enrich_data,
    load_processed_files,
    save_processed_files,
    SCHEMA_NAME,
    TABLE_NAME,
    TARGET_KEYS,
)

if __name__ == "__main__":
    process_and_upload()