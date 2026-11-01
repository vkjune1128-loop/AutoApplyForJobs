"""SQLite session management and DB helper functions."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Generator

from sqlmodel import Session, SQLModel, create_engine, select, func

from autoapply.tracker.models import Application, Job, TailoredResume
from autoapply.utils.logger import get_logger

logger = get_logger(__name__)


def get_engine(db_path: str) -> object:
    """Create a SQLAlchemy/SQLModel engine for the given SQLite path.

    Args:
        db_path: Filesystem path for the SQLite database file.

    Returns:
        SQLAlchemy Engine.
    """
    # Ensure parent directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    url = f"sqlite:///{db_path}"
    engine = create_engine(url, echo=False)
    logger.info(f"Database engine created: {url}")
    return engine


def init_db(engine: object) -> None:
    """Create all tables if they don't exist.

    Args:
        engine: SQLAlchemy Engine.
    """
    SQLModel.metadata.create_all(engine)  # type: ignore[arg-type]
    logger.info("Database tables initialized")


@contextmanager
def get_session(engine: object) -> Generator[Session, None, None]:
    """Yield a SQLModel session, auto-committing on success.

    Args:
        engine: SQLAlchemy Engine.

    Yields:
        A SQLModel Session.
    """
    session = Session(engine)  # type: ignore[arg-type]
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def log_application(session: Session, application: Application) -> Application:
    """Insert an application record into the database.

    Args:
        session: Active SQLModel session.
        application: Application model to persist.

    Returns:
        The persisted Application with its generated id.
    """
    session.add(application)
    session.commit()
    session.refresh(application)
    logger.info(
        f"Logged application #{application.id}: "
        f"{application.platform} — {application.status}"
    )
    return application


def get_today_count(
    session: Session,
    platform: str | None = None,
    status: str | None = None,
) -> int:
    """Count applications made today, optionally filtered by platform and status.

    Args:
        session: Active SQLModel session.
        platform: Optional platform name filter.
        status: Optional status filter.

    Returns:
        Number of matching applications today.
    """
    today_start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)

    statement = select(func.count()).select_from(Application).where(
        Application.applied_at >= today_start
    )

    if platform:
        statement = statement.where(Application.platform == platform)
    if status:
        statement = statement.where(Application.status == status)

    count = session.exec(statement).one()
    return count  # type: ignore[return-value]


def is_job_applied(session: Session, job_url: str) -> bool:
    """Check whether a job URL has already been applied to (any status except 'failed').

    Args:
        session: Active SQLModel session.
        job_url: The URL to check.

    Returns:
        True if a successful or dry-run application exists for this URL.
    """
    # First find the job
    statement = select(Job).where(Job.url == job_url)
    job = session.exec(statement).first()

    if not job:
        return False

    # Check for any non-failed application
    app_statement = (
        select(Application)
        .where(Application.job_id == job.id)
        .where(Application.status.in_(["applied", "dry_run"]))  # type: ignore[union-attr]
    )
    result = session.exec(app_statement).first()
    return result is not None


def save_job(session: Session, job_data: dict) -> Job:
    """Upsert a job record by URL.

    Args:
        session: Active SQLModel session.
        job_data: Dict of Job fields.

    Returns:
        The persisted Job.
    """
    existing = session.exec(
        select(Job).where(Job.url == job_data.get("url", ""))
    ).first()

    if existing:
        for key, value in job_data.items():
            if hasattr(existing, key) and value:
                setattr(existing, key, value)
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    job = Job(**job_data)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job
