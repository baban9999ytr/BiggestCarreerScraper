#!/usr/bin/env python3
"""
scripts/export_openapi.py
─────────────────────────
CLI script to dump the OpenAPI JSON schema to a file.
"""

import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.openapi import export_openapi_schema

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "openapi.json"
    export_openapi_schema(out)
    print(f"Exported OpenAPI schema to {out}")
