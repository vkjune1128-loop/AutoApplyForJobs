"""Simple TF-based keyword extraction and matching from job descriptions."""

from __future__ import annotations

import re
from collections import Counter

from autoapply.utils.logger import get_logger

logger = get_logger(__name__)

# Common English stop words to exclude from keyword extraction
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
    "role", "work", "working", "team", "experience", "ability", "strong",
    "looking", "join", "company", "including", "well", "etc", "using",
})


def extract_keywords(text: str, top_n: int = 30) -> dict:
    """Extract keywords from text using term-frequency analysis.

    Args:
        text: Raw job description text.
        top_n: Maximum number of keywords to return.

    Returns:
        Dict with ``keywords`` (list of (word, count) tuples) and
        ``bigrams`` (list of (bigram, count) tuples).
    """
    logger.info("Extracting keywords via TF analysis")

    # Normalize
    clean = text.lower()
    clean = re.sub(r"[^a-z0-9\s\+\#\.\/\-]", " ", clean)

    tokens = clean.split()
    tokens = [t.strip(".-/") for t in tokens if len(t) > 1]

    # Unigrams
    filtered = [t for t in tokens if t not in _STOP_WORDS and len(t) > 2]
    unigram_counts = Counter(filtered)

    # Bigrams (two-word phrases like "spring boot", "machine learning")
    bigrams: list[str] = []
    for i in range(len(tokens) - 1):
        if tokens[i] not in _STOP_WORDS and tokens[i + 1] not in _STOP_WORDS:
            bigram = f"{tokens[i]} {tokens[i + 1]}"
            bigrams.append(bigram)

    bigram_counts = Counter(bigrams)

    return {
        "keywords": unigram_counts.most_common(top_n),
        "bigrams": bigram_counts.most_common(top_n // 2),
    }


def compute_match_score(resume_keywords: set[str], jd_keywords: set[str]) -> float:
    """Compute Jaccard similarity between resume and JD keyword sets.

    Args:
        resume_keywords: Set of keywords from the resume.
        jd_keywords: Set of keywords from the job description.

    Returns:
        Jaccard similarity coefficient (0.0 to 1.0).
    """
    if not resume_keywords and not jd_keywords:
        return 0.0

    # Normalize to lowercase for comparison
    resume_lower = {k.lower() for k in resume_keywords}
    jd_lower = {k.lower() for k in jd_keywords}

    intersection = resume_lower & jd_lower
    union = resume_lower | jd_lower

    score = len(intersection) / len(union) if union else 0.0

    logger.info(
        f"Match score: {score:.2%} "
        f"({len(intersection)} matched out of {len(jd_lower)} JD keywords)"
    )

    return score
