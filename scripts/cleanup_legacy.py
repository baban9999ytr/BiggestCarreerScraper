#!/usr/bin/env python3
"""
scripts/cleanup_legacy.py
─────────────────────────
Safely audits and removes obsolete legacy files and isolates experimental mockups.
"""

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LEGACY_FILES_TO_DELETE = [
    ROOT / "api.pyold",
    ROOT / "main_pyside.py.old",
    ROOT / "extractor_api.py",
    ROOT / "extractor_automation.py",
    ROOT / "extract_Debug.py",
    ROOT / "extract_openapi.py",
    ROOT / ".giti",
    ROOT / "extractor",
    ROOT / "logging_optout.json",
    ROOT / "logging_optout.txt",
]

HTML_FILES_TO_ISOLATE = [
    "clean.html",
    "clean_pretty.html",
    "captcha_2fa_handler.html",
]

ACTIVE_CODE_PATHS = [
    ROOT / "app",
    ROOT / "main.py",
    ROOT / "automation.py",
    ROOT / "automation_process_jobs.py",
    ROOT / "automation_extract_candidate_details.py",
    ROOT / "config.py",
    ROOT / "models.py",
    ROOT / "schemas.py",
    ROOT / "supabaser.py",
    ROOT / "tests",
]


def check_active_references(filename: str) -> list[str]:
    """Returns any active code files that still reference filename."""
    found_in = []
    for base_path in ACTIVE_CODE_PATHS:
        if not base_path.exists():
            continue
        if base_path.is_file():
            content = base_path.read_text(encoding="utf-8", errors="ignore")
            if filename in content:
                found_in.append(str(base_path.name))
        elif base_path.is_dir():
            for file_path in base_path.rglob("*.py"):
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if filename in content:
                    found_in.append(str(file_path.relative_to(ROOT)))
    return found_in


def run_cleanup():
    print("Running safety checks on legacy files...")
    has_errors = False
    for file_path in LEGACY_FILES_TO_DELETE:
        if file_path.exists():
            refs = check_active_references(file_path.name)
            if refs:
                print(f"ERROR: {file_path.name} is still referenced in: {refs}")
                has_errors = True

    if has_errors:
        print("Safety checks failed. Aborting cleanup.")
        sys.exit(1)

    print("Safety checks passed. Deleting legacy files...")
    for file_path in LEGACY_FILES_TO_DELETE:
        if file_path.exists():
            try:
                if file_path.is_dir():
                    shutil.rmtree(file_path)
                else:
                    file_path.unlink()
                print(f"  Deleted: {file_path.name}")
            except Exception as e:
                print(f"  Failed to delete {file_path.name}: {e}")

    # Isolate test HTML files
    html_target_dir = ROOT / "html_stuff"
    html_target_dir.mkdir(exist_ok=True)
    print("Isolating HTML experiments into html_stuff/...")
    for html_file in HTML_FILES_TO_ISOLATE:
        src = ROOT / html_file
        if src.exists():
            dest = html_target_dir / html_file
            shutil.move(str(src), str(dest))
            print(f"  Moved: {html_file} -> html_stuff/{html_file}")

    print("Cleanup completed successfully.")


if __name__ == "__main__":
    run_cleanup()
