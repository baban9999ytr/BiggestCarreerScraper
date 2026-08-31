import pytest

from app.core.export_security import ExportSecurityError, safe_export_path


def test_safe_export_path_valid(tmp_path):
    valid_name = "kariyer_jobs_abc123_def456.json"
    dummy_file = tmp_path / valid_name
    dummy_file.write_text("{}", encoding="utf-8")

    file_path = safe_export_path(str(tmp_path), valid_name)
    assert file_path == dummy_file


def test_safe_export_path_traversal_rejection(tmp_path):
    evil_names = [
        "../secret.txt",
        "..\\secret.txt",
        "../../etc/passwd",
        "nested/sub/file.json",
        "kariyer_jobs.exe",
    ]
    for name in evil_names:
        with pytest.raises(ExportSecurityError):
            safe_export_path(str(tmp_path), name)
