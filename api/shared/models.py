"""SQLAlchemy models for Learn to Cloud progress tracking."""

from datetime import UTC, datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
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


class User(Base):
    """User model - synced from Clerk via webhooks."""
    __tablename__ = "users"
    
    id: Mapped[str] = mapped_column(String(255), primary_key=True)  # Clerk user ID
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )  # From Clerk OAuth
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
        Enum(SubmissionType, name="submission_type", native_enum=False),
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
