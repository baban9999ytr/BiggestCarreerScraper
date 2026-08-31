#!/usr/bin/env python3
"""
scripts/cleanup_root.py
───────────────────────
Finalizes Phase 4 repository hygiene by moving static assets and purging stale files.
"""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent


def run_root_cleanup():
    print("Starting Phase 4 root cleanup...")

    # 1. Relocate index.html to public/
    index_html = ROOT / "index.html"
    public_dir = ROOT / "public"
    public_dir.mkdir(exist_ok=True)
    if index_html.exists():
        shutil.move(str(index_html), str(public_dir / "index.html"))
        print("  Moved: index.html -> public/index.html")

    # 2. Remove obsolete root export_openapi.py since it moved to app/core/openapi.py
    root_export_openapi = ROOT / "export_openapi.py"
    if root_export_openapi.exists():
        root_export_openapi.unlink()
        print("  Deleted root export_openapi.py (migrated to app/core/openapi.py)")

    # 3. Purge stale scrape test output and empty folders
    stale_items = [
        ROOT / "extracted_cvs.json",
        ROOT / "sessions",
    ]
    for item in stale_items:
        if item.exists():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            print(f"  Purged: {item.name}")

    print("Phase 4 root cleanup completed successfully.")


if __name__ == "__main__":
    run_root_cleanup()
