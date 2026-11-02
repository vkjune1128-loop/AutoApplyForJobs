"""Unit tests for direct ATS feed crawlers (Lever & Greenhouse)."""

import json
from unittest.mock import MagicMock, patch
from autoapply.core.ats_feeds import discover_lever_jobs, discover_greenhouse_jobs, discover_direct_ats_jobs


def test_discover_lever_jobs_parsing():
    """Verify that Lever postings are filtered and structured correctly."""
    mock_postings = [
        {
            "text": "Senior Backend Engineer - Java",
            "categories": {"location": "Bengaluru"},
            "descriptionPlain": "We are seeking a senior backend engineer with deep Java and microservices experience.",
            "hostedUrl": "https://jobs.lever.co/cred/test-job-id-1",
        },
        {
            "text": "Content Writer",
            "categories": {"location": "Bengaluru"},
            "descriptionPlain": "Write marketing copies.",
            "hostedUrl": "https://jobs.lever.co/cred/test-job-id-2",
        },
    ]

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_postings).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        jobs = discover_lever_jobs(companies=["cred"], keywords=["backend", "java"])

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Senior Backend Engineer - Java"
    assert jobs[0]["company"] == "Cred"
    assert jobs[0]["platform"] == "direct_ats"
    assert "https://jobs.lever.co/cred/test-job-id-1" == jobs[0]["url"]


def test_discover_greenhouse_jobs_parsing():
    """Verify that Greenhouse postings are filtered and HTML is stripped."""
    mock_data = {
        "jobs": [
            {
                "id": 12345,
                "title": "Staff Software Engineer - Platform",
                "location": {"name": "Bangalore"},
                "content": "<p>Build <strong>distributed systems</strong> using Spring Boot and Kafka.</p>",
                "absolute_url": "https://job-boards.greenhouse.io/inmobi/jobs/12345",
            },
            {
                "id": 67890,
                "title": "HR Manager",
                "location": {"name": "Bangalore"},
                "content": "<p>Talent management.</p>",
                "absolute_url": "https://job-boards.greenhouse.io/inmobi/jobs/67890",
            },
        ]
    }

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_data).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        jobs = discover_greenhouse_jobs(companies=["inmobi"], keywords=["platform", "software"])

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Staff Software Engineer - Platform"
    assert jobs[0]["company"] == "Inmobi"
    assert "<p>" not in jobs[0]["jd_text"]
    assert "distributed systems" in jobs[0]["jd_text"]
