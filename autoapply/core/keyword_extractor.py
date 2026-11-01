"""ATS Keyword Extractor with technical taxonomy and smart synonym matching."""

from __future__ import annotations

import re
from collections import Counter

from autoapply.utils.logger import get_logger

logger = get_logger(__name__)

# Common English and job advertisement stop words to exclude
_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "need", "must",
    "it", "its", "this", "that", "these", "those", "i", "you", "we",
    "they", "he", "she", "me", "him", "her", "us", "them", "my", "your",
    "our", "their", "what", "which", "who", "whom", "where", "when", "how",
    "all", "each", "every", "both", "few", "more", "most", "other", "some",
    "such", "no", "not", "only", "same", "so", "than", "too", "very",
    "just", "about", "above", "after", "again", "also", "as", "because",
    "before", "between", "during", "if", "into", "through", "under",
    "until", "up", "while", "any", "here", "there", "then", "once",
    # Job ad boilerplate
    "role", "work", "working", "team", "experience", "ability", "strong",
    "looking", "join", "company", "including", "well", "etc", "using",
    "seeking", "years", "candidate", "ideal", "responsibilities",
    "requirements", "qualifications", "overview", "plus", "preferred",
    "hands", "hands-on", "proficient", "knowledge", "good", "excellent",
    "skills", "proven", "track", "record", "delivery", "support",
    "help", "build", "create", "make", "take", "bring", "high",
    "perform", "performing", "level", "solutions", "environment",
    "fast", "paced", "customer", "business", "product", "cross",
    "functional", "contribute", "participate", "daily", "standards",
})

# Known tech skills taxonomy for precision ATS matching
KNOWN_TECH_TERMS = [
    "java", "java 8", "java 11", "java 17", "core java",
    "spring boot", "spring mvc", "spring data jpa", "spring security", "spring cloud", "spring",
    "microservices", "microservices architecture", "rest", "rest api", "restful apis", "restful",
    "apache kafka", "kafka", "event-driven architecture", "event driven", "asynchronous messaging", "rabbitmq", "activemq",
    "sql server", "mysql", "postgresql", "oracle", "sql", "nosql", "redis", "mongodb",
    "hibernate", "jpa", "orm",
    "aws", "aws s3", "s3", "docker", "kubernetes", "cloud",
    "junit", "mockito", "test-driven development", "tdd", "unit testing", "integration testing",
    "maven", "gradle", "jenkins", "ci/cd", "git", "github", "gitlab", "jira", "agile", "scrum",
    "dynatrace", "prometheus", "grafana", "sonarqube", "apache poi",
    "multithreading", "concurrency", "distributed systems", "batch processing", "caching",
    "system design", "performance optimization", "data ingestion",
]


def extract_keywords(text: str, top_n: int = 30) -> dict:
    """Extract technical keywords from text using domain taxonomy + TF analysis.

    Returns:
        Dict with ``keywords`` (list of (word, count) tuples) and
        ``bigrams`` (list of (bigram, count) tuples).
    """
    logger.info("Extracting keywords via technical taxonomy & TF analysis")
    text_lower = text.lower()

    # 1. Identify multi-word and known technical terms present in the JD
    found_tech: list[str] = []
    for term in KNOWN_TECH_TERMS:
        pattern = r"\b" + re.escape(term) + r"\b"
        if re.search(pattern, text_lower):
            found_tech.append(term)

    # 2. General unigram TF analysis for any additional domain terms
    clean = re.sub(r"[^a-z0-9\s\+\#\.\/\-]", " ", text_lower)
    tokens = [t.strip(".-/") for t in clean.split() if len(t) > 1]
    filtered_unigrams = [
        t for t in tokens
        if t not in _STOP_WORDS and len(t) > 2 and not t.isdigit()
    ]
    unigram_counts = Counter(filtered_unigrams)

    # 3. Bigrams
    bigrams: list[str] = []
    for i in range(len(tokens) - 1):
        w1, w2 = tokens[i], tokens[i + 1]
        if w1 not in _STOP_WORDS and w2 not in _STOP_WORDS and not w1.isdigit() and not w2.isdigit():
            bigrams.append(f"{w1} {w2}")
    bigram_counts = Counter(bigrams)

    # Prioritize recognized technical terms
    tech_counter = Counter({t: 5 for t in found_tech})
    combined_keywords = (tech_counter + unigram_counts).most_common(top_n)

    return {
        "keywords": combined_keywords,
        "bigrams": bigram_counts.most_common(top_n // 2),
        "tech_terms": found_tech,
    }


def compute_match_score(resume_keywords: set[str], jd_keywords: set[str]) -> float:
    """Compute ATS keyword coverage (recall) of JD requirements in the resume.

    ATS engines check what percentage of the JD's required skills the candidate possesses.
    """
    if not jd_keywords:
        return 1.0

    resume_lower = {k.lower().strip() for k in resume_keywords}
    jd_lower = {k.lower().strip() for k in jd_keywords if k.lower().strip() not in _STOP_WORDS}

    if not jd_lower:
        return 1.0

    matched = 0
    for kw in jd_lower:
        # Direct match or substring match (e.g. 'kafka' in 'apache kafka')
        if any(kw in rk or rk in kw for rk in resume_lower):
            matched += 1

    score = matched / len(jd_lower)
    logger.info(f"ATS Keyword Coverage: {score:.1%} ({matched}/{len(jd_lower)} requirements matched)")
    return score
