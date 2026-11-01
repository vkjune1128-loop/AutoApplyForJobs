"""Tests for ATS compatibility parser."""

import tempfile
from pathlib import Path
from autoapply.core.ats_parser import check_ats_compatibility


def test_check_ats_compatibility_nonexistent():
    res = check_ats_compatibility("non_existent_file.pdf")
    assert not res["text_extractable"]
    assert len(res["warnings"]) > 0


def test_check_ats_compatibility_empty_file():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"")
        temp_path = f.name

    try:
        res = check_ats_compatibility(temp_path)
        assert not res["text_extractable"]
    finally:
        Path(temp_path).unlink(missing_ok=True)
