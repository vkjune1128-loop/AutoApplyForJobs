"""SQLModel data models for tracking jobs, applications, and tailored resumes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class Job(SQLModel, table=True):
    """A scraped job listing."""

    __tablename__ = "jobs"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    platform: str = Field(index=True)
    title: str
    company: str
    location: str = ""
    url: str = Field(index=True, unique=True)
    jd_text: str = ""
    posted_date: str = ""
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Application(SQLModel, table=True):
    """Record of a job application attempt."""

    __tablename__ = "applications"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    job_id: int | None = Field(default=None, foreign_key="jobs.id", index=True)
    platform: str = Field(index=True)
    status: str = Field(index=True)  # "applied", "skipped", "failed", "dry_run"
    tailored_resume_path: str = ""
    ats_score: int | None = None
    applied_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: str = ""


class TailoredResume(SQLModel, table=True):
    """Record of a resume tailored for a specific job."""

    __tablename__ = "tailored_resumes"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    job_id: int | None = Field(default=None, foreign_key="jobs.id", index=True)
    original_hash: str = ""
    tailored_summary: str = ""
    matched_keywords: str = ""  # JSON-serialized list
    ats_score: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
