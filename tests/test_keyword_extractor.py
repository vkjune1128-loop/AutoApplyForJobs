"""Tests for keyword extractor."""

from autoapply.core.keyword_extractor import compute_match_score, extract_keywords


def test_extract_keywords():
    sample_jd = (
        "We are looking for a Senior Java Developer with strong experience in "
        "Spring Boot, Microservices, Kafka, and PostgreSQL. Experience with Docker "
        "and Kubernetes is a plus."
    )
    result = extract_keywords(sample_jd, top_n=10)
    keywords = [kw for kw, _ in result["keywords"]]
    assert "java" in keywords or "spring" in keywords
    assert "bigrams" in result


def test_compute_match_score():
    resume_keywords = {"java", "spring", "docker", "postgresql"}
    jd_keywords = {"java", "spring", "kubernetes", "kafka"}

    score = compute_match_score(resume_keywords, jd_keywords)
    assert 0.0 < score < 1.0

    # Exact match test
    assert compute_match_score({"java"}, {"java"}) == 1.0

    # No match test
    assert compute_match_score({"python"}, {"java"}) == 0.0
