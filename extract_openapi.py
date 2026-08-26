from __future__ import annotations

import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("exporter")


def export_openapi_schema(output_path: str = "openapi.json") -> bool:
    try:
        from main import app

        app.openapi_schema = None
        schema = app.openapi()

        abs_path = os.path.abspath(output_path)
        with open(abs_path, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2)

        if os.path.exists(abs_path) and os.path.getsize(abs_path) > 0:
            logger.info(
                "[SUCCESS] openapi.json exported to '%s' (%d bytes, %d paths indexed).",
                abs_path,
                os.path.getsize(abs_path),
                len(schema.get("paths", {})),
            )
            return True
        else:
            logger.error("[ERROR] Export file '%s' was created but is empty.", abs_path)
            return False

    except Exception as err:
        logger.error("[ERROR] Failed to generate openapi.json: %s", err)
        return False


if __name__ == "__main__":
    success = export_openapi_schema()
    sys.exit(0 if success else 1)