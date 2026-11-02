"""Unit tests for GitHub Issues manager and two-way sync."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from sqlmodel import Session, SQLModel, create_engine, select

from autoapply.config.settings import Settings
from autoapply.platforms.github_issues import create_or_update_digest_issue, sync_closed_issues_to_db
from autoapply.tracker.models import Application, Job


def test_create_or_update_digest_issue_payload():
    """Verify that GitHub Issue body has candidate mention, job table, and proper labels."""
    items = [
        {
            "company": "Meesho",
            "role": "Java Lead",
            "score": 90,
            "url": "https://jobs.lever.co/meesho/123",
            "pdf_name": "Vikas_Kumar_Meesho.pdf",
            "cover_note": "Great fit.",
            "referral_note": "Can you refer me?",
        }
    ]
    settings = Settings(
        github_token="fake_token",
        github_repo="test-user/test-repo",
        github_username="vikaskumar",
    )

    mock_open_issues: list = []
    mock_created = {"number": 42}

    def mock_api(endpoint, method="GET", data=None, token=""):
        if "state=open" in endpoint:
            return mock_open_issues
        if method == "POST" and endpoint.endswith("/issues"):
            assert data["labels"] == ["daily-digest", "ready-to-apply"]
            assert "@vikaskumar" in data["body"]
            assert "Meesho" in data["body"]
            assert "90%" in data["body"]
            return mock_created
        return {}

    with patch("autoapply.platforms.github_issues._github_api_request", side_effect=mock_api):
        num = create_or_update_digest_issue(items, "Vikas Kumar", settings)

    assert num == 42


def test_sync_closed_issues_to_db(tmp_path):
    """Verify that closed issues mark corresponding applications as applied."""
    db_file = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_file}")
    SQLModel.metadata.create_all(engine)

    # Insert a ready_to_apply application
    with Session(engine) as session:
        job = Job(
            platform="naukri",
            title="Senior Java Dev",
            company="Swiggy",
            url="https://swiggy.com/job/1",
        )
        session.add(job)
        session.commit()
        session.refresh(job)

        app = Application(
            job_id=job.id,
            platform="naukri",
            status="ready_to_apply",
        )
        session.add(app)
        session.commit()

    settings = Settings(
        github_token="fake_token",
        github_repo="test-user/test-repo",
    )

    mock_closed = [
        {
            "number": 15,
            "body": "| **Swiggy** | Senior Java Dev | 95% | [Apply](url) |",
            "labels": [{"name": "daily-digest"}],
            "closed_at": "2026-11-03T05:30:00Z",
        }
    ]

    def mock_api(endpoint, method="GET", data=None, token=""):
        if "state=closed" in endpoint:
            return mock_closed
        if "comments" in endpoint:
            return []  # No comments -> all in issue marked applied
        if "labels" in endpoint and method == "POST":
            assert data == {"labels": ["synced"]}
            return {}
        return {}

    with patch("autoapply.platforms.github_issues._github_api_request", side_effect=mock_api):
        synced = sync_closed_issues_to_db(engine, settings)

    assert synced == 1

    # Verify status in DB is now 'applied'
    with Session(engine) as session:
        app_in_db = session.exec(select(Application)).first()
        assert app_in_db.status == "applied"
