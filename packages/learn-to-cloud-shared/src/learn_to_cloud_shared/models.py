"""SQLAlchemy models for Learn to Cloud progress tracking."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from learn_to_cloud_shared.core.database import Base


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
    verification_jobs: Mapped[list["VerificationJob"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    step_progress: Mapped[list["StepProgress"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class SubmissionType(StrEnum):
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
    # CODE_ANALYSIS kept so SQLAlchemy can deserialize old rows during
    # rolling deploys before the 0015 migration converts them to ci_status.
    CODE_ANALYSIS = "code_analysis"
    PR_REVIEW = "pr_review"
    JOURNAL_API_VERIFIER = "journal_api_verifier"

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
        Index(
            "ix_submissions_user_verified_updated",
            "user_id",
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
            text("created_at DESC"),
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
    attempt_number: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"), default=1
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
    # True when verification logic actually ran (not blocked by server error).
    # Only count completed verification attempts.
    verification_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    # JSON-serialized task feedback for multi-task verification submissions
    # Stores list of TaskResult dicts so feedback persists across page reloads
    feedback_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # User-facing validation error message (persists across page reloads)
    validation_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Cloud provider for multi-cloud labs ("aws", "azure", "gcp", or None)
    cloud_provider: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )

    user: Mapped["User"] = relationship(back_populates="submissions")
    verification_jobs: Mapped[list["VerificationJob"]] = relationship(
        back_populates="result_submission"
    )


class VerificationJob(TimestampMixin, Base):
    """Work-queue marker for asynchronous verification execution.

    A row exists during in-flight Durable orchestration. The persist
    activity links a ``Submission`` via ``result_submission_id`` when
    work completes; the poller deletes the row if Durable reports
    terminal failure. PR4 dropped the legacy ``status`` enum, the
    ``mark_*`` lifecycle methods, and the Postgres-side error /
    timestamp columns — Durable owns runtime state, ``Submission``
    owns the outcome.
    """

    __tablename__ = "verification_jobs"
    __table_args__ = (
        Index(
            "ix_verification_jobs_user_req_created",
            "user_id",
            "requirement_id",
            "created_at",
        ),
        Index(
            "uq_verification_jobs_active_user_requirement_v2",
            "user_id",
            "requirement_id",
            unique=True,
            postgresql_where=text("result_submission_id IS NULL"),
        ),
        Index(
            "ix_verification_jobs_user_phase_active",
            "user_id",
            "phase_id",
            postgresql_where=text("result_submission_id IS NULL"),
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
    requirement_id: Mapped[str] = mapped_column(String(100), nullable=False)
    phase_id: Mapped[int] = mapped_column(Integer, nullable=False)
    submission_type: Mapped[SubmissionType] = mapped_column(
        Enum(
            SubmissionType,
            name="submission_type",
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    submitted_value: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cloud_provider: Mapped[str | None] = mapped_column(String(16), nullable=True)
    result_submission_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("submissions.id", ondelete="SET NULL"),
        nullable=True,
    )
    traceparent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped["User"] = relationship(back_populates="verification_jobs")
    result_submission: Mapped["Submission | None"] = relationship(
        back_populates="verification_jobs"
    )


class StepProgress(Base):
    """Tracks completion of learning steps within topics.

    Note: Only has completed_at timestamp since steps are immutable once done.
    """

    __tablename__ = "step_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "topic_id", "step_id", name="uq_user_topic_step"),
        Index("ix_step_progress_user_topic", "user_id", "topic_id"),
        Index("ix_step_progress_user_phase", "user_id", "phase_id"),
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


# ---------------------------------------------------------------------------
# Curriculum tables (issue #463 / Phase B of #461)
#
# These tables hold the curriculum content authored in YAML. Phase B is
# additive only: the sync function writes to them on deploy but the app
# still reads from YAML at runtime. User-state tables do NOT reference
# these yet; that comes in Phase D.
#
# All curriculum entities:
#   * use UUID primary keys (issue #462)
#   * support soft-delete via ``deleted_at`` (Q3 of #461)
#   * use ON DELETE RESTRICT on FKs (Q4 of #461)
#   * have a ``legacy_id`` column preserving the original YAML string id
#     so Phase D can backfill user_state.*_id -> *.uuid via this column
# ---------------------------------------------------------------------------


class CurriculumPhase(TimestampMixin, Base):
    """A curriculum phase (stored copy of YAML _phase.yaml metadata)."""

    __tablename__ = "phases"
    __table_args__ = (
        Index(
            "uq_phases_slug_active",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    uuid: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    legacy_id: Mapped[int] = mapped_column(Integer, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    short_description: Mapped[str] = mapped_column(Text, nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CurriculumTopic(TimestampMixin, Base):
    """A topic within a curriculum phase."""

    __tablename__ = "topics"
    __table_args__ = (
        Index(
            "uq_topics_phase_slug_active",
            "phase_uuid",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    uuid: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    phase_uuid: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("phases.uuid", ondelete="RESTRICT", name="fk_topics_phase_uuid"),
        nullable=False,
    )
    legacy_id: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CurriculumStep(TimestampMixin, Base):
    """A learning step within a curriculum topic."""

    __tablename__ = "steps"
    __table_args__ = (
        Index(
            "uq_steps_topic_order_active",
            "topic_uuid",
            "order",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    uuid: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    topic_uuid: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("topics.uuid", ondelete="RESTRICT", name="fk_steps_topic_uuid"),
        nullable=False,
    )
    legacy_id: Mapped[str] = mapped_column(Text, nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Bundled per-step extras (options, checklist, tips, done_when).
    # Bundled rather than split out because Phase B doesn't need to query
    # these individually; split later if Phase C-and-beyond needs it.
    extra_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CurriculumLearningObjective(TimestampMixin, Base):
    """A learning objective for a curriculum topic."""

    __tablename__ = "learning_objectives"
    __table_args__ = (
        Index(
            "uq_learning_objectives_topic_order_active",
            "topic_uuid",
            "order",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    uuid: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    topic_uuid: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "topics.uuid",
            ondelete="RESTRICT",
            name="fk_learning_objectives_topic_uuid",
        ),
        nullable=False,
    )
    legacy_id: Mapped[str] = mapped_column(Text, nullable=False)
    text_: Mapped[str] = mapped_column("text", Text, nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CurriculumRequirement(TimestampMixin, Base):
    """A hands-on requirement for a curriculum phase.

    The ``submission_type`` is stored as plain text rather than the
    SubmissionType enum because the canonical type-discrimination
    lives in the Pydantic discriminated union (#470), which keeps
    type_config aligned. The DB just stores whatever string the sync
    wrote.
    """

    __tablename__ = "requirements"
    __table_args__ = (
        Index(
            "uq_requirements_phase_id_active",
            "phase_uuid",
            "id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Requirement IDs are globally unique because user-state tables
        # store the bare string id (e.g. "github-profile"); two
        # requirements sharing an id in different phases would make
        # Phase D's UUID backfill ambiguous.
        Index(
            "uq_requirements_id_active",
            "id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    uuid: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    phase_uuid: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "phases.uuid",
            ondelete="RESTRICT",
            name="fk_requirements_phase_uuid",
        ),
        nullable=False,
    )
    id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    submission_type: Mapped[str] = mapped_column(Text, nullable=False)
    type_config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
