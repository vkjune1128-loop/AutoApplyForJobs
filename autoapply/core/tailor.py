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
- NEVER add or invent certifications. If the master resume has no certifications, the certifications list MUST be empty [].
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
            genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=12))
            if api_key
            else None
        )

    def _local_keyword_extraction(self, jd_text: str) -> dict:
        """Deterministic keyword extraction fallback when API is slow or offline."""
        logger.info("Using local keyword extraction fallback")
        tf_res = extract_keywords(jd_text, top_n=25)
        tech_terms = [t.title() for t in tf_res.get("tech_terms", [])]
        other_kw = [word.capitalize() for word, _ in tf_res["keywords"] if word.title() not in tech_terms]
        all_skills = tech_terms + other_kw

        return {
            "required_skills": all_skills[:8] if all_skills else ["Java", "Spring Boot", "Microservices"],
            "preferred_skills": all_skills[8:16] if len(all_skills) > 8 else ["Docker", "Kubernetes", "Kafka"],
            "role_keywords": [phrase.title() for phrase, _ in tf_res["bigrams"]][:8],
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

        # 1. Dynamically identify Target Role
        target_role = "Java Backend Engineer"
        jd_lower = jd_text.lower()
        if "kafka" in jd_lower:
            target_role = "Software Engineer (Java / Kafka)"
        elif "senior" in jd_lower:
            target_role = "Senior Java Backend Engineer"
        elif "microservices" in jd_lower:
            target_role = "Java Microservices Backend Engineer"

        # 2. Dynamically align Professional Summary
        top_reqs = [kw for kw in jd_keywords.get("required_skills", []) if kw.lower() in [s.lower() for s in resume.skills]]
        top_skills_str = ", ".join(top_reqs[:3]) if top_reqs else "Core Java, Spring Boot, and Microservices"
        tailored_summary = (
            f"Results-driven {target_role} and Assistant Manager with 4+ years of professional experience "
            f"architecting, developing, and deploying mission-critical distributed systems and enterprise microservices "
            f"using {top_skills_str} at Samsung SDS. Deep technical expertise in event-driven streaming, "
            f"relational/NoSQL database performance tuning, and scalable API design. Proven track record of solo module "
            f"leadership, reducing bulk data ingestion latency by 60%, and enforcing SonarQube engineering standards."
        )

        # 3. Prioritize skills that match JD keywords to the very top
        matched_skills = [s for s in resume.skills if any(kw in s.lower() or s.lower() in kw for kw in all_jd_kw)]
        other_skills = [s for s in resume.skills if s not in matched_skills]
        reordered_skills = matched_skills + other_skills

        # 4. For experience, prioritize bullets with matching keywords
        tailored_experiences = []
        for exp in resume.experience:
            matching_bullets = [
                b for b in exp.bullets if any(kw in b.lower() for kw in all_jd_kw)
            ]
            non_matching = [b for b in exp.bullets if b not in matching_bullets]
            exp_dict = exp.model_dump()
            exp_dict["bullets"] = matching_bullets + non_matching
            tailored_experiences.append(exp_dict)

        # 5. Check relocation preference from JD location
        target_loc = resume.location or "Gurgaon, India"
        for city in ["bengaluru", "bangalore", "hyderabad", "pune", "mumbai", "noida", "chennai"]:
            if city in jd_lower and "gurgaon" in target_loc.lower() and "relocation" not in target_loc.lower():
                target_loc = f"Gurgaon, India (Open to Relocation to {city.capitalize()})"
                break

        data = resume.model_dump()
        data["summary"] = tailored_summary
        data["skills"] = reordered_skills
        data["experience"] = tailored_experiences
        data["matched_keywords"] = list(all_jd_kw)
        data["target_role"] = target_role
        data["location"] = target_loc

        # Strict BGV Safety: Never invent certifications. Preserve only what user provided in master resume.
        data["certifications"] = list(resume.certifications) if resume.certifications else []

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

    def generate_referral_note(self, resume: ResumeData, company: str, role: str) -> str:
        """Generate a crisp internal referral pitch for current employees on Grapevine / LinkedIn."""
        return (
            f"Hi! Hope you're doing well. I noticed the {role} opening at {company} and would love to be considered. "
            f"I am currently Assistant Manager at Samsung SDS with 4+ years of experience architecting Core Java, Spring Boot, "
            f"and Kafka microservices processing 10M+ daily transactions. Would you be open to submitting an internal referral for me? "
            f"I can share my resume and relevant details right away. Thanks in advance!"
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
        resume_text_parts_lower = [p.lower() for p in resume_text_parts]

        all_keywords = set(
            jd_keywords.get("required_skills", [])
            + jd_keywords.get("preferred_skills", [])
            + jd_keywords.get("role_keywords", [])
        )

        matched = []
        missing = []
        for kw in all_keywords:
            kw_clean = kw.lower().strip()
            # Direct containment
            if kw_clean in resume_text:
                matched.append(kw)
            # Reverse containment (e.g. resume has 'apache kafka', keyword is 'kafka')
            elif any(kw_clean in part for part in resume_text_parts_lower):
                matched.append(kw)
            # Significant token match for compound terms (e.g. 'microservices architecture' -> 'microservices')
            elif any(w in resume_text for w in kw_clean.split() if len(w) >= 4 and w not in ["with", "from", "data"]):
                matched.append(kw)
            else:
                missing.append(kw)

        # Weight required skills heavier than preferred/role keywords
        req_skills = set(jd_keywords.get("required_skills", []))
        req_matched = [k for k in req_skills if k in matched]
        req_ratio = len(req_matched) / max(len(req_skills), 1)

        total_ratio = len(matched) / max(len(all_keywords), 1)
        # Combined score: 60% weight on required skills, 40% on overall keywords
        score = int((0.6 * req_ratio + 0.4 * total_ratio) * 100)
        score = min(max(score, 30), 98)

        return {
            "score": score,
            "matched": matched,
            "missing": missing,
        }
