import json
from pathlib import Path

def export_openapi_schema(output_path: str = "openapi.json") -> None:
    from main import app
    schema = app.openapi()
    Path(output_path).write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")