"""Resume tailoring engine powered by Gemini API."""

from __future__ import annotations

import json

from google import genai
from google.genai import types

from autoapply.config.schemas import ResumeData, TailoredResume
from autoapply.utils.logger import get_logger

logger = get_logger(__name__)

# System prompts with guardrails
_KEYWORD_SYSTEM_PROMPT = """\
You are an expert ATS keyword extractor. Given a job description, extract and categorize keywords.
Return a JSON object with these keys:
- "required_skills": list of explicitly required technical skills
- "preferred_skills": list of nice-to-have / preferred skills
- "role_keywords": list of role-specific domain keywords (e.g., "distributed systems", "CI/CD")
- "action_verbs": list of action verbs from the JD (e.g., "designed", "led", "optimized")
"""

_TAILOR_SYSTEM_PROMPT = """\
You are a professional resume writer who tailors resumes to match job descriptions.

CRITICAL GUARDRAILS:
- NEVER fabricate technologies, metrics, or experiences.
- ONLY reframe, emphasize, and reorder existing content.
- You may rephrase bullet points to highlight relevant skills.
- You may reorder skills and experience sections to prioritize JD-relevant items.
- You may adjust the summary section to align with the role.
- Preserve all factual information (dates, company names, titles).

Given the candidate's resume data and JD keywords, return a tailored resume as JSON matching
the TailoredResume schema.
"""

_COVER_NOTE_SYSTEM_PROMPT = """\
You are a professional networking expert. Write a concise 3-sentence LinkedIn outreach/cover note.
Sentence 1: Express interest in the role and company.
Sentence 2: Highlight the most relevant experience/skill match.
Sentence 3: Call to action (e.g., "I'd love to discuss how I can contribute").
Keep it under 300 characters total. Be genuine, not generic.
"""

_ATS_SCORE_SYSTEM_PROMPT = """\
You are an ATS scoring expert. Given a resume and JD keywords, estimate an ATS match score.
Return a JSON object with:
- "score": integer 0-100 representing match percentage
- "matched": list of keywords found in the resume
- "missing": list of keywords NOT found in the resume
"""


class ResumeTailor:
    """AI-powered resume tailoring using Google Gemini."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self.model = model
        self.client = genai.Client(api_key=api_key)

    def extract_jd_keywords(self, jd_text: str) -> dict:
        """Extract structured keywords from a job description.

        Args:
            jd_text: Raw job description text.

        Returns:
            Dict with required_skills, preferred_skills, role_keywords, action_verbs.
        """
        logger.info("Extracting keywords from JD")

        response = self.client.models.generate_content(
            model=self.model,
            contents=f"Extract keywords from this job description:\n\n{jd_text}",
            config=types.GenerateContentConfig(
                system_instruction=_KEYWORD_SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )

        try:
            result = json.loads(response.text)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse keyword extraction response, returning empty dict")
            result = {
                "required_skills": [],
                "preferred_skills": [],
                "role_keywords": [],
                "action_verbs": [],
            }

        return result

    def tailor_resume(
        self, resume: ResumeData, jd_text: str, jd_keywords: dict
    ) -> TailoredResume:
        """Tailor a resume to match a job description.

        Args:
            resume: The candidate's master resume data.
            jd_text: Raw job description text.
            jd_keywords: Extracted keywords from the JD.

        Returns:
            A TailoredResume with reframed bullets and reordered skills.
        """
        logger.info("Tailoring resume for JD")

        prompt = (
            f"Tailor this resume to match the job description.\n\n"
            f"## Resume Data\n```json\n{resume.model_dump_json(indent=2)}\n```\n\n"
            f"## Job Description\n{jd_text}\n\n"
            f"## Extracted JD Keywords\n```json\n{json.dumps(jd_keywords, indent=2)}\n```\n\n"
            f"Return the tailored resume as JSON matching the TailoredResume schema with fields: "
            f"name, email, phone, linkedin_url, github_url, summary, skills, experience, "
            f"education, certifications, target_role, matched_keywords."
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_TAILOR_SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.3,
            ),
        )

        try:
            data = json.loads(response.text)
            tailored = TailoredResume.model_validate(data)
        except (json.JSONDecodeError, TypeError, Exception) as e:
            logger.warning(f"Failed to parse tailored resume: {e}. Using original resume.")
            tailored = TailoredResume(**resume.model_dump())

        return tailored

    def generate_cover_note(self, resume: ResumeData, jd_text: str) -> str:
        """Generate a 3-sentence LinkedIn outreach note.

        Args:
            resume: The candidate's resume data.
            jd_text: Raw job description text.

        Returns:
            A short, personalized cover note string.
        """
        logger.info("Generating cover note")

        prompt = (
            f"Write a LinkedIn outreach note for this candidate applying to this role.\n\n"
            f"## Candidate Summary\n{resume.summary}\n\n"
            f"## Key Skills\n{', '.join(resume.skills[:10])}\n\n"
            f"## Job Description\n{jd_text[:1000]}"
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_COVER_NOTE_SYSTEM_PROMPT,
                temperature=0.7,
            ),
        )

        return response.text or ""

    def estimate_ats_score(self, resume: ResumeData, jd_keywords: dict) -> dict:
        """Estimate ATS match score between resume and JD keywords.

        Args:
            resume: The candidate's resume data.
            jd_keywords: Extracted keywords from the JD.

        Returns:
            Dict with score (int), matched (list), and missing (list).
        """
        logger.info("Estimating ATS score")

        # Build a text representation of the resume for matching
        resume_text_parts = [
            resume.summary,
            ", ".join(resume.skills),
        ]
        for exp in resume.experience:
            resume_text_parts.extend(exp.bullets)
            resume_text_parts.extend(exp.technologies)

        resume_text = " ".join(resume_text_parts).lower()

        # Quick local match before hitting the API
        all_keywords = set(
            jd_keywords.get("required_skills", [])
            + jd_keywords.get("preferred_skills", [])
            + jd_keywords.get("role_keywords", [])
        )

        matched = [kw for kw in all_keywords if kw.lower() in resume_text]
        missing = [kw for kw in all_keywords if kw.lower() not in resume_text]

        score = int((len(matched) / max(len(all_keywords), 1)) * 100)

        return {
            "score": score,
            "matched": matched,
            "missing": missing,
        }
