"""Pydantic schemas for configuration data."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# Resume Data Models
# ──────────────────────────────────────────────


class Experience(BaseModel):
    """A single work experience entry."""

    company: str
    title: str
    start_date: str
    end_date: str = "Present"
    location: str = ""
    bullets: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class Education(BaseModel):
    """A single education entry."""

    institution: str
    degree: str
    field: str
    year: str
    gpa: str | None = None


class ResumeData(BaseModel):
    """Structured resume data loaded from master_resume.yaml."""

    name: str
    email: str
    phone: str
    location: str = "Gurgaon, India"
    linkedin_url: str = ""
    github_url: str = ""
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)


class TailoredResume(BaseModel):
    """A resume tailored to a specific job description."""

    name: str
    email: str
    phone: str
    location: str = "Gurgaon, India"
    linkedin_url: str = ""
    github_url: str = ""
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    target_role: str = ""
    matched_keywords: list[str] = Field(default_factory=list)


# ──────────────────────────────────────────────
# Job Filter Configuration
# ──────────────────────────────────────────────


class JobFilter(BaseModel):
    """Search criteria for a job platform."""

    keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    experience_level: str = ""
    experience_range: str = ""
    remote_only: bool = False
    easy_apply_only: bool = False
    date_posted: str = ""
    blacklisted_companies: list[str] = Field(default_factory=list)


# ──────────────────────────────────────────────
# Form Answers (for screening questions)
# ──────────────────────────────────────────────


class FormAnswers(BaseModel):
    """Pre-filled answers for common screening questions on job platforms."""

    years_of_experience: dict[str, int] = Field(default_factory=dict)
    current_ctc: str = ""
    expected_ctc: str = ""
    notice_period: str = ""
    phone: str = ""
    visa_status: str = ""
    willing_to_relocate: bool = True
    authorized_to_work: bool = True
    require_sponsorship: bool = False
    custom_answers: dict[str, str] = Field(default_factory=dict)
