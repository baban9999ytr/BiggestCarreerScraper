"""
models.py (Compatibility Shim)
──────────────────────────────
Legacy import path re-exporting from app.models.session and app.models.schemas.
"""
from app.models.schemas import *
from app.models.session import *