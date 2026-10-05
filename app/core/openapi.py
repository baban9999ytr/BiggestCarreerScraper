"""
app/core/openapi.py
───────────────────
Helper to export OpenAPI JSON schema from the FastAPI application.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def export_openapi_schema(output_path: str = "openapi.json") -> Dict[str, Any]:
    from main import app

    schema = app.openapi()
    Path(output_path).write_text(
        json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return schema
