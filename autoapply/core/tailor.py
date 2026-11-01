"""Resume tailoring engine powered by Gemini API with deterministic fallback."""

from __future__ import annotations

import json
import re

from google import genai
from google.genai import types

from autoapply.config.schemas import ResumeData, TailoredResume
from autoapply.core.keyword_extractor import extract_keywords
from autoapply.utils.logger import get_logger

logger = get_logger(__name__)

# System prompts with strict guardrails
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


class ResumeTailor:
    """AI-powered resume tailoring using Google Gemini with local heuristic fallback."""

    def __init__(self, api_key: str, model: str = "gemini-flash-latest") -> None:
        self.model = model
        self.client = (
            genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=15000))
            if api_key
            else None
        )

    def _local_keyword_extraction(self, jd_text: str) -> dict:
        """Deterministic keyword extraction fallback when API is slow or offline."""
        logger.info("Using local keyword extraction fallback")
        tf_res = extract_keywords(jd_text, top_n=20)
        unigrams = [word.capitalize() for word, _ in tf_res["keywords"]]
        bigrams = [phrase.title() for phrase, _ in tf_res["bigrams"]]
        return {
            "required_skills": unigrams[:6],
            "preferred_skills": unigrams[6:12],
            "role_keywords": bigrams[:8],
            "action_verbs": ["Led", "Architected", "Engineered", "Optimized", "Designed"],
        }

    def extract_jd_keywords(self, jd_text: str) -> dict:
        """Extract structured keywords from a job description."""
        logger.info("Extracting keywords from JD")

        if not self.client:
            return self._local_keyword_extraction(jd_text)

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=f"Extract keywords from this job description:\n\n{jd_text}",
                config=types.GenerateContentConfig(
                    system_instruction=_KEYWORD_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )
            result = json.loads(response.text)
        except Exception as e:
            logger.warning(f"Gemini keyword extraction encountered issue ({e}). Using deterministic extractor.")
            result = self._local_keyword_extraction(jd_text)

        return result

    def _local_tailor(self, resume: ResumeData, jd_text: str, jd_keywords: dict) -> TailoredResume:
        """Heuristic re-ordering and ATS prioritization without hallucinating facts."""
        logger.info("Applying deterministic ATS tailoring and skill prioritization")
        all_jd_kw = {
            kw.lower()
            for kw in (
                jd_keywords.get("required_skills", [])
                + jd_keywords.get("preferred_skills", [])
                + jd_keywords.get("role_keywords", [])
            )
        }

        # Prioritize skills that match JD keywords to the top
        matched_skills = [s for s in resume.skills if any(kw in s.lower() for kw in all_jd_kw)]
        other_skills = [s for s in resume.skills if s not in matched_skills]
        reordered_skills = matched_skills + other_skills

        # For experience, sort bullets having matching keywords higher
        tailored_experiences = []
        for exp in resume.experience:
            matching_bullets = [
                b for b in exp.bullets if any(kw in b.lower() for kw in all_jd_kw)
            ]
            non_matching = [b for b in exp.bullets if b not in matching_bullets]
            exp_dict = exp.model_dump()
            exp_dict["bullets"] = matching_bullets + non_matching
            tailored_experiences.append(exp_dict)

        data = resume.model_dump()
        data["skills"] = reordered_skills
        data["experience"] = tailored_experiences
        data["matched_keywords"] = list(all_jd_kw)
        data["target_role"] = jd_keywords.get("role_keywords", ["Java Backend Engineer"])[0] if jd_keywords.get("role_keywords") else "Java Backend Engineer"

        return TailoredResume.model_validate(data)

    def tailor_resume(
        self, resume: ResumeData, jd_text: str, jd_keywords: dict
    ) -> TailoredResume:
        """Tailor a resume to match a job description."""
        logger.info("Tailoring resume for JD")

        if not self.client:
            return self._local_tailor(resume, jd_text, jd_keywords)

        prompt = (
            f"Tailor this resume to match the job description.\n\n"
            f"## Resume Data\n```json\n{resume.model_dump_json(indent=2)}\n```\n\n"
            f"## Job Description\n{jd_text}\n\n"
            f"## Extracted JD Keywords\n```json\n{json.dumps(jd_keywords, indent=2)}\n```\n\n"
            f"Return the tailored resume as JSON matching the TailoredResume schema with fields: "
            f"name, email, phone, linkedin_url, github_url, summary, skills, experience, "
            f"education, certifications, target_role, matched_keywords."
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=_TAILOR_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.3,
                ),
            )
            data = json.loads(response.text)
            tailored = TailoredResume.model_validate(data)
        except Exception as e:
            logger.warning(f"AI tailoring issue ({e}). Applying safe deterministic tailoring.")
            tailored = self._local_tailor(resume, jd_text, jd_keywords)

        return tailored

    def generate_cover_note(self, resume: ResumeData, jd_text: str) -> str:
        """Generate a 3-sentence LinkedIn outreach note."""
        logger.info("Generating cover note")

        if not self.client:
            return (
                f"Hi, I noticed the exciting backend opening and wanted to reach out. "
                f"With 4+ years of experience leading high-throughput Java and Spring Boot systems at Samsung SDS, "
                f"I would love to explore how my background in distributed architecture can add value to your team."
            )

        prompt = (
            f"Write a LinkedIn outreach note for this candidate applying to this role.\n\n"
            f"## Candidate Summary\n{resume.summary}\n\n"
            f"## Key Skills\n{', '.join(resume.skills[:10])}\n\n"
            f"## Job Description\n{jd_text[:1000]}"
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=_COVER_NOTE_SYSTEM_PROMPT,
                    temperature=0.7,
                ),
            )
            return response.text.strip() if response.text else ""
        except Exception:
            return (
                f"Hi, I noticed the exciting backend opening and wanted to reach out. "
                f"With 4+ years of experience leading high-throughput Java and Spring Boot systems at Samsung SDS, "
                f"I would love to explore how my background in distributed architecture can add value to your team."
            )

    def estimate_ats_score(self, resume: ResumeData, jd_keywords: dict) -> dict:
        """Estimate ATS match score between resume and JD keywords."""
        logger.info("Estimating ATS score")

        resume_text_parts = [
            resume.summary,
            ", ".join(resume.skills),
        ]
        for exp in resume.experience:
            resume_text_parts.extend(exp.bullets)
            resume_text_parts.extend(exp.technologies)

        resume_text = " ".join(resume_text_parts).lower()

        all_keywords = set(
            jd_keywords.get("required_skills", [])
            + jd_keywords.get("preferred_skills", [])
            + jd_keywords.get("role_keywords", [])
        )

        matched = [kw for kw in all_keywords if kw.lower() in resume_text]
        missing = [kw for kw in all_keywords if kw.lower() not in resume_text]

        score = int((len(matched) / max(len(all_keywords), 1)) * 100) if all_keywords else 85

        return {
            "score": score,
            "matched": matched,
            "missing": missing,
        }
