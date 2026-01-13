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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


def today() -> date:
    """Return current UTC date."""
    return datetime.now(UTC).date()


class User(Base):
    """User model - synced from Clerk via webhooks."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)  # Clerk user ID
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )  # From Clerk OAuth
    is_profile_public: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )

    # Relationships
    github_submissions: Mapped[list["GitHubSubmission"]] = relationship(
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

    id: Mapped[str] = mapped_column(String(255), primary_key=True)  # svix-id
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        index=True,
    )


class SubmissionType(str, PyEnum):
    """Type of submission for hands-on verification."""

    PROFILE_README = "profile_readme"  # GitHub profile README
    REPO_FORK = "repo_fork"  # Fork of a required repository
    DEPLOYED_APP = "deployed_app"  # Deployed application URL
    CTF_TOKEN = "ctf_token"  # CTF completion token verification


class GitHubSubmission(Base):
    """Tracks validated GitHub submissions for hands-on verification."""

    __tablename__ = "github_submissions"
    __table_args__ = (
        UniqueConstraint("user_id", "requirement_id", name="uq_user_requirement"),
        Index("ix_github_submissions_user_phase", "user_id", "phase_id"),
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
    )  # e.g., "phase1-profile-readme", "phase1-linux-ctfs-fork"
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
    submitted_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )  # The submitted URL (GitHub or deployed app)
    github_username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )  # Username extracted from URL (null for deployed apps)
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="github_submissions")


class ActivityType(str, PyEnum):
    """Type of user activity for streak tracking."""

    QUESTION_ATTEMPT = "question_attempt"  # Attempted a knowledge question
    STEP_COMPLETE = "step_complete"  # Completed a learning step
    TOPIC_COMPLETE = "topic_complete"  # Completed all questions for a topic
    CERTIFICATE_EARNED = "certificate_earned"  # Earned a completion certificate


class Certificate(Base):
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
    )  # "full_completion" or "phase_X"
    verification_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )  # Unique code for certificate verification
    recipient_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )  # Name as it appears on certificate
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
    topics_completed: Mapped[int] = mapped_column(Integer, nullable=False)
    total_topics: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="certificates")


class QuestionAttempt(Base):
    """Tracks user attempts at LLM-graded knowledge questions."""

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
    )  # e.g., "phase1-topic4"
    question_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )  # e.g., "phase1-topic4-q1"
    user_answer: Mapped[str] = mapped_column(Text, nullable=False)
    is_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    llm_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="question_attempts")


class StepProgress(Base):
    """Tracks completion of learning steps within topics."""

    __tablename__ = "step_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "topic_id", "step_order", name="uq_user_topic_step"),
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
    )  # e.g., "phase1-topic5"
    step_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )  # The order/number of the step (1, 2, 3, etc.)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="step_progress")


class UserActivity(Base):
    """Tracks user activities for streak calculation."""

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
    )  # e.g., topic_id or question_id for context
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="activities")
