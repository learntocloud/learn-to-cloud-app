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
    checklist_progress: Mapped[list["ChecklistProgress"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    github_submissions: Mapped[list["GitHubSubmission"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    question_attempts: Mapped[list["QuestionAttempt"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    daily_reflections: Mapped[list["DailyReflection"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    activities: Mapped[list["UserActivity"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class ChecklistProgress(Base):
    """Tracks user progress on checklist items (both phase and topic level)."""

    __tablename__ = "checklist_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "checklist_item_id", name="uq_user_checklist"),
        Index("ix_checklist_progress_user_phase", "user_id", "phase_id"),
        Index("ix_checklist_progress_user_item", "user_id", "checklist_item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    checklist_item_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )  # e.g., "phase0-check1" or "phase1-topic1-check1"
    phase_id: Mapped[int] = mapped_column(Integer, nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(
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
    user: Mapped["User"] = relationship(back_populates="checklist_progress")


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
    TOPIC_COMPLETE = "topic_complete"  # Completed all questions for a topic
    REFLECTION = "reflection"  # Submitted a daily reflection


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


class DailyReflection(Base):
    """Tracks daily reflections and AI-generated personalized greetings."""

    __tablename__ = "daily_reflections"
    __table_args__ = (
        UniqueConstraint("user_id", "reflection_date", name="uq_user_reflection_date"),
        Index("ix_daily_reflections_user_date", "user_id", "reflection_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    reflection_date: Mapped[date] = mapped_column(Date, nullable=False, default=today)
    reflection_text: Mapped[str] = mapped_column(Text, nullable=False)
    ai_greeting: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )  # Generated greeting for next visit
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
    user: Mapped["User"] = relationship(back_populates="daily_reflections")


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
