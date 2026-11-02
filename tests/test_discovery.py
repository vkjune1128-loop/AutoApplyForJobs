"""Unit tests for multi-source job discovery."""

import json
from unittest.mock import MagicMock, patch
from autoapply.core.discovery import discover_instahyre_jobs


def test_discover_instahyre_jobs_parsing():
    """Verify that Instahyre API payload parses into standard job format."""
    mock_payload = {
        "objects": [
            {
                "title": "Lead Backend Engineer (Java)",
                "employer": {
                    "company_name": "Razorpay",
                    "company_tagline": "Powering payments for India",
                    "instahyre_note": "Fintech payment gateway",
                },
                "locations": "Bangalore",
                "keywords": ["Java", "Spring Boot", "Kafka", "Microservices"],
                "public_url": "https://www.instahyre.com/job-123-razorpay/",
            },
            {
                "title": "Frontend React Engineer",
                "employer": {
                    "company_name": "SomeCorp",
                },
                "locations": "Bangalore",
                "keywords": ["React", "CSS", "HTML"],
                "public_url": "https://www.instahyre.com/job-456-somecorp/",
            },
        ]
    }

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        jobs = discover_instahyre_jobs(locations=["Bangalore"], max_jobs=5)

    # Only Java role should match, Frontend React role excluded
    assert len(jobs) == 1
    assert jobs[0]["company"] == "Razorpay"
    assert jobs[0]["title"] == "Lead Backend Engineer (Java)"
    assert jobs[0]["platform"] == "instahyre"
    assert "Kafka" in jobs[0]["jd_text"]
