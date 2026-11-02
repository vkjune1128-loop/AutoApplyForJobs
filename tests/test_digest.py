"""Unit tests for presentation layer dashboard and digest generation."""

from pathlib import Path
from autoapply.presentation.digest import render_copilot_html, render_daily_digest_markdown


def test_render_copilot_html_with_referral(tmp_path: Path):
    """Verify HTML generation contains referral pitch buttons and job cards."""
    items = [
        {
            "company": "Meesho",
            "role": "Senior Backend Engineer",
            "platform": "direct_ats",
            "location": "Bengaluru",
            "score": 88,
            "url": "https://jobs.lever.co/meesho/123",
            "pdf_path": "data/generated_resumes/Vikas_Kumar_Meesho.pdf",
            "pdf_name": "Vikas_Kumar_Meesho.pdf",
            "cover_note": "Hi, I am keen to apply.",
            "referral_note": "Hi! Could you refer me for the Senior Backend Engineer role?",
            "recommended": True,
        }
    ]

    out_file = tmp_path / "dashboard.html"
    render_copilot_html(items, "Vikas Kumar", out_file)

    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "Meesho" in content
    assert "88% ATS" in content
    assert "Employee Referral Pitch" in content
    assert "Copy Referral Pitch" in content
    assert "Vikas_Kumar_Meesho.pdf" in content


def test_render_daily_digest_markdown_with_history(tmp_path: Path):
    """Verify Markdown digest output includes action queue and application history."""
    items = [
        {
            "company": "CRED",
            "role": "Backend Lead",
            "platform": "direct_ats",
            "location": "Bengaluru",
            "score": 90,
            "url": "https://jobs.lever.co/cred/456",
            "pdf_name": "Vikas_Kumar_CRED.pdf",
            "cover_note": "Excited for this role.",
            "referral_note": "Looking for a referral at CRED.",
        }
    ]
    applied_items = [
        {
            "company": "Samsung SDS",
            "role": "Assistant Manager",
            "platform": "internal",
            "score": 95,
            "applied_at": "2026-03-01 10:00 UTC",
            "pdf_name": "Vikas_Kumar_Samsung.pdf",
        }
    ]

    out_file = tmp_path / "DAILY_DIGEST.md"
    render_daily_digest_markdown(items, "Vikas Kumar", out_file, applied_items=applied_items)

    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "Daily Job & Resume Action Digest" in content
    assert "CRED" in content
    assert "Submitted Applications History" in content
    assert "Samsung SDS" in content
    assert "Referral Pitch" in content
