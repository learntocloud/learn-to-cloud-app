"""SQLAlchemy models for Learn to Cloud progress tracking."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
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


class SubmissionValueKind(StrEnum):
    """Storage shape for a submitted verification value."""

    GITHUB_URL = "github_url"
    TOKEN = "token"
    DEPLOYED_URL = "deployed_url"
    TEXT = "text"


class Submission(TimestampMixin, Base):
    """Tracks validated submissions for hands-on verification.

    References curriculum via ``requirement_uuid`` (FK to
    ``requirements.uuid``). Phase D.2 of #461 / #465 dropped the legacy
    denormalized ``requirement_id`` / ``submission_type`` / ``phase_id``
    columns and the ``attempt_number`` counter (per #460) -- callers
    derive those values from the joined ``Requirement`` row when
    needed.
    """

    __tablename__ = "submissions"
    __table_args__ = (
        CheckConstraint(
            "is_validated IS FALSE OR validated_at IS NOT NULL",
            name="ck_submissions_validated_at_when_validated",
        ),
        CheckConstraint(
            "is_validated IS FALSE OR verification_completed IS TRUE",
            name="ck_submissions_completed_when_validated",
        ),
        CheckConstraint(
            """
            (
                submission_value_kind = 'github_url'
                AND github_url IS NOT NULL
                AND token_value IS NULL
                AND deployed_url IS NULL
                AND text_value IS NULL
                AND submitted_value = github_url
            )
            OR (
                submission_value_kind = 'token'
                AND token_value IS NOT NULL
                AND github_url IS NULL
                AND deployed_url IS NULL
                AND text_value IS NULL
                AND submitted_value = token_value
            )
            OR (
                submission_value_kind = 'deployed_url'
                AND deployed_url IS NOT NULL
                AND github_url IS NULL
                AND token_value IS NULL
                AND text_value IS NULL
                AND submitted_value = deployed_url
            )
            OR (
                submission_value_kind = 'text'
                AND text_value IS NOT NULL
                AND github_url IS NULL
                AND token_value IS NULL
                AND deployed_url IS NULL
                AND submitted_value = text_value
            )
            """,
            name="ck_submissions_typed_value_shape",
        ),
        CheckConstraint(
            """
            (
                github_url IS NULL
                OR github_url ~* '^https://github[.]com/[^[:space:]]+$'
            )
            AND (
                deployed_url IS NULL
                OR deployed_url ~* '^https?://[^[:space:]]+$'
            )
            AND (
                token_value IS NULL
                OR length(btrim(token_value)) > 0
            )
            AND (
                text_value IS NULL
                OR length(btrim(text_value)) > 0
            )
            """,
            name="ck_submissions_typed_value_format",
        ),
        ForeignKeyConstraint(
            ["requirement_uuid", "submission_value_kind"],
            ["requirements.uuid", "requirements.submission_value_kind"],
            name="fk_submissions_requirement_value_kind",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_submissions_user_verified_updated",
            "user_id",
            "verification_completed",
            "updated_at",
        ),
        Index(
            "ix_submissions_user_req_uuid_latest",
            "user_id",
            "requirement_uuid",
            text("created_at DESC"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    requirement_uuid: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "requirements.uuid",
            ondelete="RESTRICT",
            name="fk_submissions_requirement_uuid",
        ),
        nullable=False,
    )
    submitted_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    submission_value_kind: Mapped[str] = mapped_column(Text, nullable=False)
    github_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    deployed_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_value: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    # Structured per-task feedback for multi-task verification
    # submissions, stored as JSONB. Each element is a TaskResult shape
    # (``task_name``, ``passed``, ``feedback``, ``next_steps``). Now that
    # we surface rubric feedback for passing submissions too (#425),
    # every multi-task verification persists a payload.
    feedback_json: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
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
        CheckConstraint(
            """
            (
                submission_value_kind = 'github_url'
                AND github_url IS NOT NULL
                AND token_value IS NULL
                AND deployed_url IS NULL
                AND text_value IS NULL
                AND submitted_value = github_url
            )
            OR (
                submission_value_kind = 'token'
                AND token_value IS NOT NULL
                AND github_url IS NULL
                AND deployed_url IS NULL
                AND text_value IS NULL
                AND submitted_value = token_value
            )
            OR (
                submission_value_kind = 'deployed_url'
                AND deployed_url IS NOT NULL
                AND github_url IS NULL
                AND token_value IS NULL
                AND text_value IS NULL
                AND submitted_value = deployed_url
            )
            OR (
                submission_value_kind = 'text'
                AND text_value IS NOT NULL
                AND github_url IS NULL
                AND token_value IS NULL
                AND deployed_url IS NULL
                AND submitted_value = text_value
            )
            """,
            name="ck_verification_jobs_typed_value_shape",
        ),
        CheckConstraint(
            """
            (
                github_url IS NULL
                OR github_url ~* '^https://github[.]com/[^[:space:]]+$'
            )
            AND (
                deployed_url IS NULL
                OR deployed_url ~* '^https?://[^[:space:]]+$'
            )
            AND (
                token_value IS NULL
                OR length(btrim(token_value)) > 0
            )
            AND (
                text_value IS NULL
                OR length(btrim(text_value)) > 0
            )
            """,
            name="ck_verification_jobs_typed_value_format",
        ),
        ForeignKeyConstraint(
            ["requirement_uuid", "submission_value_kind"],
            ["requirements.uuid", "requirements.submission_value_kind"],
            name="fk_verification_jobs_requirement_value_kind",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_verification_jobs_user_req_uuid_created",
            "user_id",
            "requirement_uuid",
            "created_at",
        ),
        Index(
            "uq_verification_jobs_active_user_req_uuid",
            "user_id",
            "requirement_uuid",
            unique=True,
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
    requirement_uuid: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "requirements.uuid",
            ondelete="RESTRICT",
            name="fk_verification_jobs_requirement_uuid",
        ),
        nullable=False,
    )
    submitted_value: Mapped[str] = mapped_column(Text, nullable=False)
    submission_value_kind: Mapped[str] = mapped_column(Text, nullable=False)
    github_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    deployed_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cloud_provider: Mapped[str | None] = mapped_column(String(16), nullable=True)
    result_submission_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("submissions.id", name="fk_verification_jobs_result_submission_id"),
        nullable=True,
    )
    traceparent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped["User"] = relationship(back_populates="verification_jobs")
    result_submission: Mapped["Submission | None"] = relationship(
        back_populates="verification_jobs"
    )


class StepProgress(Base):
    """Tracks completion of learning steps within topics.

    References the curriculum via ``step_uuid`` (FK to ``steps.uuid``).
    Phase D.1c (#465) dropped the legacy ``topic_id`` / ``step_id`` /
    ``phase_id`` / ``step_order`` denormalized columns; that data is now
    derived from the FK join when needed.
    """

    __tablename__ = "step_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "step_uuid", name="uq_step_progress_user_step"),
        Index("ix_step_progress_step_uuid", "step_uuid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_uuid: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "steps.uuid",
            ondelete="RESTRICT",
            name="fk_step_progress_step_uuid",
        ),
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
# These tables hold the curriculum content authored in YAML. The sync
# function writes to them on deploy; the app reads from them at runtime
# via content_db_loader (Phase C).
#
# All curriculum entities:
#   * use UUID primary keys (issue #462)
#   * support soft-delete via ``deleted_at`` (Q3 of #461)
#   * use ON DELETE RESTRICT on FKs (Q4 of #461)
# Topics, steps, and requirements carry a ``slug`` -- the kebab-case
# human-readable id from YAML (matches the YAML filename or the inline
# slug field). Phases use ``slug`` (e.g. "phase0") + ``order`` (int 0-6)
# as the human keys; learning_objectives are identified solely by uuid.
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
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    short_description: Mapped[str] = mapped_column(Text, nullable=False)
    order: Mapped[int] = mapped_column(BigInteger, nullable=False)
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
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    order: Mapped[int] = mapped_column(BigInteger, nullable=False)
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
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    order: Mapped[int] = mapped_column(BigInteger, nullable=False)
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
    text_: Mapped[str] = mapped_column("text", Text, nullable=False)
    order: Mapped[int] = mapped_column(BigInteger, nullable=False)
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
        CheckConstraint(
            """
            (
                submission_type IN (
                    'github_profile',
                    'profile_readme',
                    'repo_fork',
                    'pr_review',
                    'journal_api_verifier',
                    'devops_analysis',
                    'security_scanning',
                    'ci_status'
                )
                AND submission_value_kind = 'github_url'
            )
            OR (
                submission_type IN (
                    'ctf_token',
                    'networking_token',
                    'iac_token'
                )
                AND submission_value_kind = 'token'
            )
            OR (
                submission_type = 'deployed_api'
                AND submission_value_kind = 'deployed_url'
            )
            OR (
                submission_type IN (
                    'journal_api_response',
                    'code_analysis'
                )
                AND submission_value_kind = 'text'
            )
            """,
            name="ck_requirements_submission_value_kind_matches_type",
        ),
        Index(
            "uq_requirements_phase_slug_active",
            "phase_uuid",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Requirement slugs are globally unique: they show up in URLs,
        # log lines, and ad-hoc queries, so two requirements sharing a
        # slug in different phases would be too easy to confuse. The
        # FK from submissions/verification_jobs targets uuid, so this
        # invariant is for humans, not the schema.
        Index(
            "uq_requirements_slug_active",
            "slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        UniqueConstraint(
            "uuid",
            "submission_value_kind",
            name="uq_requirements_uuid_value_kind",
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
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    submission_type: Mapped[str] = mapped_column(Text, nullable=False)
    submission_value_kind: Mapped[str] = mapped_column(Text, nullable=False)
    order: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )
    type_config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
