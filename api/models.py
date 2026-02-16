"""SQLAlchemy models for Learn to Cloud progress tracking."""

from datetime import UTC, datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from core.database import Base


def utcnow() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


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
    """User model - authenticated via GitHub OAuth."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("github_username", name="uq_users_github_username"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    submissions: Mapped[list["Submission"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    step_progress: Mapped[list["StepProgress"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    phase_progress: Mapped[list["UserPhaseProgress"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class SubmissionType(str, PyEnum):
    """Type of submission for hands-on verification.

    Currently supports Phase 0, Phase 1, and Phase 2 verification types.

    To add a new verification type:
    1. Add the enum value here
    2. Add a validator function in the appropriate module:
       - GitHub-based: api/services/github_hands_on_verification_service.py
       - Or create a new module for complex verification types
    3. Add the routing case in validate_submission() in hands_on_verification.py
    4. Add optional fields to HandsOnRequirement schema if needed
    """

    # Phase 0: GitHub profile setup
    GITHUB_PROFILE = "github_profile"

    # Phase 1: Profile README, repo fork, and CTF completion
    PROFILE_README = "profile_readme"
    REPO_FORK = "repo_fork"
    CTF_TOKEN = "ctf_token"

    # Phase 2: Networking lab verification
    NETWORKING_TOKEN = "networking_token"

    # Phase 3: Journal API implementation
    # JOURNAL_API_RESPONSE kept for backward compatibility with existing DB records
    JOURNAL_API_RESPONSE = "journal_api_response"
    CODE_ANALYSIS = "code_analysis"
    PR_REVIEW = "pr_review"

    # Phase 4: Cloud deployment validation
    DEPLOYED_API = "deployed_api"

    # Phase 5: DevOps analysis
    DEVOPS_ANALYSIS = "devops_analysis"

    # Phase 6: Security posture
    SECURITY_SCANNING = "security_scanning"


class Submission(TimestampMixin, Base):
    """Tracks validated submissions for hands-on verification.

    Supports multiple submission types: GitHub URLs, deployed apps, CTF tokens, etc.
    """

    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "requirement_id",
            "attempt_number",
            name="uq_user_requirement_attempt",
        ),
        Index("ix_submissions_user_phase", "user_id", "phase_id"),
        Index(
            "ix_submissions_user_phase_validated",
            "user_id",
            "phase_id",
            postgresql_where=text("is_validated"),
        ),
        Index("ix_submissions_user_updated_at", "user_id", "updated_at"),
        Index(
            "ix_submissions_user_verified_updated",
            "user_id",
            "verification_completed",
            "updated_at",
        ),
        Index(
            "ix_submissions_user_req_verified_updated",
            "user_id",
            "requirement_id",
            "verification_completed",
            "updated_at",
        ),
        Index(
            "ix_submissions_user_phase_req",
            "user_id",
            "phase_id",
            "requirement_id",
        ),
        Index(
            "ix_submissions_user_req_latest",
            "user_id",
            "requirement_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    requirement_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
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
    # True when verification logic actually ran (not blocked by server error).
    # Used for cooldown calculations - only count completed verification attempts.
    verification_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    # JSON-serialized task feedback for CODE_ANALYSIS submissions
    # Stores list of TaskResult dicts so feedback persists across page reloads
    feedback_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # User-facing validation error message (persists across page reloads)
    validation_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Cloud provider for multi-cloud labs ("aws", "azure", "gcp", or None)
    cloud_provider: Mapped[str | None] = mapped_column(String(16), nullable=True)

    user: Mapped["User"] = relationship(back_populates="submissions")


class StepProgress(Base):
    """Tracks completion of learning steps within topics.

    Note: Only has completed_at timestamp since steps are immutable once done.
    """

    __tablename__ = "step_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "topic_id", "step_id", name="uq_user_topic_step"),
        Index("ix_step_progress_user_topic", "user_id", "topic_id"),
        Index("ix_step_progress_user_phase", "user_id", "phase_id"),
        Index("ix_step_progress_completed_at", "completed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    topic_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    step_id: Mapped[str] = mapped_column(String(255), nullable=False)
    phase_id: Mapped[int] = mapped_column(Integer, nullable=False)
    step_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )

    user: Mapped["User"] = relationship(back_populates="step_progress")


class UserPhaseProgress(Base):
    """Denormalized per-user per-phase submission counts.

    Tracks validated_submissions per phase to avoid aggregate queries
    on the submissions table for every dashboard load.
    Step completion is computed live from step_progress rows.
    """

    __tablename__ = "user_phase_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "phase_id", name="uq_user_phase_progress"),
        Index("ix_user_phase_progress_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    phase_id: Mapped[int] = mapped_column(Integer, nullable=False)
    validated_submissions: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped["User"] = relationship(back_populates="phase_progress")


class AnalyticsSnapshot(Base):
    """Pre-computed analytics snapshot.

    Single-row table holding the serialized CommunityAnalytics payload.
    Updated by a background task; read by request handlers.
    Survives container restarts and is consistent across replicas.
    """

    __tablename__ = "analytics_snapshot"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_analytics_snapshot_single_row"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    data: Mapped[str] = mapped_column(Text, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )
