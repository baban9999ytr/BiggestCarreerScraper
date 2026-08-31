"""
app/core/export_security.py
────────────────────────────
Path-traversal-safe export file resolution.

All export filenames pass through ``safe_export_path()`` before a
FileResponse is served. The function rejects any filename that:

- Contains URL-encoded characters (``%``)
- Contains path separators (``/``, ``\\``)
- Does not match the strict alphanumeric pattern
- Resolves outside the configured exports directory
"""
from __future__ import annotations

import re
from pathlib import Path


_SAFE_FILENAME_RE = re.compile(
    r"^[a-zA-Z0-9][a-zA-Z0-9_\-]{0,199}\.(json|csv)$"
)


class ExportSecurityError(ValueError):
    """Raised when an export filename or path fails validation."""


def safe_export_path(export_dir: str, filename: str) -> Path:
    """
    Validate *filename* and return a resolved :class:`~pathlib.Path` that is
    guaranteed to reside inside *export_dir*.

    Args:
        export_dir: The absolute path to the exports directory (from config).
        filename:   The caller-supplied filename (path component only — no slashes).

    Returns:
        A fully resolved :class:`~pathlib.Path` pointing to the requested file.

    Raises:
        ExportSecurityError: If validation fails for any reason.

    Security properties:
    - URL-encoded separators (``%2F``, ``%5C``) are rejected early.
    - The allowlist regex blocks multi-extension files, hidden files, and
      names with special characters before any filesystem access occurs.
    - ``Path.resolve()`` is called on both the export root and the candidate
      path; ``relative_to()`` then guarantees no escape from the root.
    """
    if not filename or not isinstance(filename, str):
        raise ExportSecurityError("Filename must be a non-empty string.")

    if "%" in filename:
        raise ExportSecurityError(
            "URL-encoded characters are not permitted in export filenames."
        )

    if "/" in filename or "\\" in filename:
        raise ExportSecurityError(
            "Path separators are not permitted in export filenames."
        )

    if not _SAFE_FILENAME_RE.match(filename):
        raise ExportSecurityError(
            "Invalid export filename. "
            "Only alphanumeric characters, hyphens, and underscores are allowed, "
            "with a .json or .csv extension."
        )

    export_root = Path(export_dir).resolve()
    candidate = (export_root / filename).resolve()

    try:
        candidate.relative_to(export_root)
    except ValueError:
        raise ExportSecurityError(
            "Requested file is outside the permitted export directory."
        )

    if not candidate.is_file():
        raise ExportSecurityError("Export file not found.")

    return candidate
