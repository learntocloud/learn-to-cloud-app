"""SQLAlchemy models for learner accounts and progress."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from learn_to_cloud_shared.core.database import Base


def utcnow() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(UTC)


class TimestampMixin:
    """Add creation and update timestamps."""

    @declared_attr
    def created_at(cls) -> Mapped[datetime]:
        return mapped_column(DateTime(timezone=True), default=utcnow)

    @declared_attr
    def updated_at(cls) -> Mapped[datetime]:
        return mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class User(TimestampMixin, Base):
    """GitHub-authenticated learner."""

    __tablename__ = "users"
    __table_args__ = (Index("ix_users_github_username", "github_username"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_username: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)


class SubmissionType(StrEnum):
    """Supported hands-on verification types."""

    PROFILE_README = "profile_readme"
    REPO_FORK = "repo_fork"
    CTF_TOKEN = "ctf_token"
    NETWORKING_TOKEN = "networking_token"
    JOURNAL_API_VERIFIER = "journal_api_verifier"
    DEPLOYED_API = "deployed_api"
    DEPLOYMENT_ARCHITECTURE = "deployment_architecture"
    DEVOPS_ANALYSIS = "devops_analysis"
    SECURITY_SCANNING = "security_scanning"
    CAREER_REFLECTION = "career_reflection"


class SubmissionValueKind(StrEnum):
    """Storage shape for a submitted verification value."""

    GITHUB_URL = "github_url"
    TOKEN = "token"
    DEPLOYED_URL = "deployed_url"
    TEXT = "text"


class VerificationAttemptOutcome(StrEnum):
    """Terminal result of a verification attempt."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SERVER_ERROR = "server_error"
    CANCELLED = "cancelled"


class VerificationSnapshotSource(StrEnum):
    """Source of an attempt's requirement snapshot."""

    SUBMITTED = "submitted"
    RECONSTRUCTED = "reconstructed"


class LearnerStepCompletion(Base):
    """Record a learner completing a catalog step UUID."""

    __tablename__ = "learner_step_completions"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    step_uuid: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
    )


class VerificationAttempt(TimestampMixin, Base):
    """One verification attempt, keyed by its Durable instance UUID."""

    __tablename__ = "verification_attempts"
    __table_args__ = (
        CheckConstraint(
            "submission_value_kind IN ('github_url', 'token', 'deployed_url', 'text')",
            name="ck_verification_attempts_value_kind",
        ),
        CheckConstraint(
            "length(btrim(submitted_value)) > 0",
            name="ck_verification_attempts_submitted_value_nonempty",
        ),
        CheckConstraint(
            "outcome IS NULL OR outcome IN "
            "('succeeded', 'failed', 'server_error', 'cancelled')",
            name="ck_verification_attempts_outcome",
        ),
        CheckConstraint(
            "(outcome IS NULL) = (completed_at IS NULL)",
            name="ck_verification_attempts_outcome_completed_at",
        ),
        CheckConstraint(
            "snapshot_source IN ('submitted', 'reconstructed')",
            name="ck_verification_attempts_snapshot_source",
        ),
        CheckConstraint(
            "snapshot_source = 'reconstructed' OR ("
            "requirement_snapshot IS NOT NULL "
            "AND requirement_snapshot_hash IS NOT NULL)",
            name="ck_verification_attempts_submitted_snapshot_present",
        ),
        Index(
            "uq_verification_attempts_active_user_req",
            "user_id",
            "requirement_uuid",
            unique=True,
            postgresql_where=text("outcome IS NULL"),
        ),
        Index(
            "ix_verification_attempts_succeeded_user_req",
            "user_id",
            "requirement_uuid",
            postgresql_where=text("outcome = 'succeeded'"),
        ),
        Index(
            "ix_verification_attempts_user_req_created",
            "user_id",
            "requirement_uuid",
            text("created_at DESC"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    requirement_uuid: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    artifact_schema_version: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    curriculum_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    requirement_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    requirement_snapshot_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_source: Mapped[str] = mapped_column(Text, nullable=False)
    payload_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    github_username_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    submission_value_kind: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_value: Mapped[str] = mapped_column(Text, nullable=False)
    cloud_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    traceparent: Mapped[str | None] = mapped_column(Text, nullable=True)

    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    feedback_json: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    validation_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    terminal_source: Mapped[str | None] = mapped_column(Text, nullable=True)
