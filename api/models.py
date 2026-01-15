"""SQLAlchemy models for Learn to Cloud progress tracking."""

from datetime import UTC, date, datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from core.database import Base


def utcnow() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


def today() -> date:
    """Return current UTC date."""
    return datetime.now(UTC).date()


class TimestampMixin:
    """Mixin that adds created_at and updated_at timestamp columns.

    Use this for any model that needs audit timestamps.
    """

    @declared_attr
    def created_at(cls) -> Mapped[datetime]:
        return mapped_column(DateTime(timezone=True), default=utcnow)

    @declared_attr
    def updated_at(cls) -> Mapped[datetime]:
        return mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class User(TimestampMixin, Base):
    """User model - synced from Clerk via webhooks."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    submissions: Mapped[list["Submission"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    question_attempts: Mapped[list["QuestionAttempt"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    activities: Mapped[list["UserActivity"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    certificates: Mapped[list["Certificate"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    step_progress: Mapped[list["StepProgress"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class ProcessedWebhook(Base):
    """Tracks processed webhooks for idempotency."""

    __tablename__ = "processed_webhooks"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        index=True,
    )


class SubmissionType(str, PyEnum):
    """Type of submission for hands-on verification.

    To add a new verification type:
    1. Add the enum value here
    2. Add a validator function in the appropriate module:
       - GitHub-based: api/shared/github_hands_on_verification.py
       - Deployment/External: api/shared/hands_on_verification.py
       - Or create a new module for complex verification types
    3. Add the routing case in validate_submission() in hands_on_verification.py
    4. Add optional fields to HandsOnRequirement schema if needed
       (e.g., expected_endpoint)
    """

    GITHUB_PROFILE = "github_profile"
    PROFILE_README = "profile_readme"
    REPO_FORK = "repo_fork"
    REPO_URL = "repo_url"

    DEPLOYED_APP = "deployed_app"

    CTF_TOKEN = "ctf_token"
    API_CHALLENGE = "api_challenge"

    # Local API response validation (paste JSON output)
    JOURNAL_API_RESPONSE = "journal_api_response"

    # DevOps verification types (Phase 5)
    WORKFLOW_RUN = "workflow_run"  # Verify GitHub Actions ran successfully
    REPO_WITH_FILES = "repo_with_files"  # Verify repo contains specific files
    CONTAINER_IMAGE = "container_image"  # Verify public container image exists


class Submission(TimestampMixin, Base):
    """Tracks validated submissions for hands-on verification.

    Supports multiple submission types: GitHub URLs, deployed apps, CTF tokens, etc.
    """

    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("user_id", "requirement_id", name="uq_user_requirement"),
        Index("ix_submissions_user_phase", "user_id", "phase_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    requirement_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    submission_type: Mapped[SubmissionType] = mapped_column(
        Enum(
            SubmissionType,
            name="submission_type",
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    phase_id: Mapped[int] = mapped_column(Integer, nullable=False)
    submitted_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    extracted_username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    user: Mapped["User"] = relationship(back_populates="submissions")


class ActivityType(str, PyEnum):
    """Type of user activity for streak and progress tracking."""

    QUESTION_ATTEMPT = "question_attempt"
    STEP_COMPLETE = "step_complete"
    TOPIC_COMPLETE = "topic_complete"
    HANDS_ON_VALIDATED = "hands_on_validated"
    PHASE_COMPLETE = "phase_complete"
    CERTIFICATE_EARNED = "certificate_earned"


class Certificate(TimestampMixin, Base):
    """Tracks completion certificates issued to users."""

    __tablename__ = "certificates"
    __table_args__ = (
        UniqueConstraint("user_id", "certificate_type", name="uq_user_certificate"),
        Index("ix_certificates_user", "user_id"),
        Index("ix_certificates_verification", "verification_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    certificate_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    verification_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )
    recipient_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
    phases_completed: Mapped[int] = mapped_column(Integer, nullable=False)
    total_phases: Mapped[int] = mapped_column(Integer, nullable=False)

    user: Mapped["User"] = relationship(back_populates="certificates")


class QuestionAttempt(Base):
    """Tracks user attempts at LLM-graded knowledge questions.

    Note: Only has created_at, no updated_at since attempts are immutable.
    """

    __tablename__ = "question_attempts"
    __table_args__ = (
        Index("ix_question_attempts_user_topic", "user_id", "topic_id"),
        Index("ix_question_attempts_user_question", "user_id", "question_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    topic_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    question_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    user_answer: Mapped[str] = mapped_column(Text, nullable=False)
    is_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    llm_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )

    user: Mapped["User"] = relationship(back_populates="question_attempts")


class StepProgress(Base):
    """Tracks completion of learning steps within topics.

    Note: Only has completed_at timestamp since steps are immutable once done.
    """

    __tablename__ = "step_progress"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "topic_id", "step_order", name="uq_user_topic_step"
        ),
        Index("ix_step_progress_user_topic", "user_id", "topic_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    topic_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    step_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )

    user: Mapped["User"] = relationship(back_populates="step_progress")


class UserActivity(Base):
    """Tracks user activities for streak calculation.

    Note: Only has created_at since activities are immutable event logs.
    """

    __tablename__ = "user_activities"
    __table_args__ = (
        Index("ix_user_activities_user_date", "user_id", "activity_date"),
        Index("ix_user_activities_user_type", "user_id", "activity_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    activity_type: Mapped[ActivityType] = mapped_column(
        Enum(
            ActivityType,
            name="activity_type",
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    activity_date: Mapped[date] = mapped_column(Date, nullable=False, default=today)
    reference_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )

    user: Mapped["User"] = relationship(back_populates="activities")
