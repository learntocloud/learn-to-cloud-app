"""Repository for verification attempts and compare-and-set finalization."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Integer,
    Uuid,
    and_,
    column,
    delete,
    exists,
    func,
    literal,
    select,
    text,
    union_all,
    update,
    values,
)
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.models import (
    Submission,
    VerificationAttempt,
    VerificationAttemptOutcome,
    VerificationSnapshotSource,
    utcnow,
)
from learn_to_cloud_shared.submission_values import SubmittedValue

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AttemptPrepareState:
    """Immutable identity + submitted snapshot needed to run an attempt."""

    id: UUID
    user_id: int
    requirement_uuid: UUID
    snapshot_source: str
    payload_version: int | None
    requirement_snapshot: dict | None
    requirement_snapshot_hash: str | None
    submission_value_kind: str
    submitted_value: str
    github_username_snapshot: str | None
    cloud_provider: str | None
    traceparent: str | None
    outcome: str | None
    started_at: datetime | None
    legacy_job_id: UUID | None


@dataclass(frozen=True, slots=True)
class AttemptTerminalState:
    """Terminal projection of an attempt after finalization."""

    id: UUID
    outcome: str | None
    error_code: str | None
    validation_message: str | None
    terminal_source: str | None
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class AttemptStatusRow:
    """Lifecycle projection used by the stale-attempt reconciler."""

    id: UUID
    user_id: int
    requirement_uuid: UUID
    outcome: str | None
    started_at: datetime | None
    created_at: datetime
    legacy_job_id: UUID | None


@dataclass(frozen=True, slots=True)
class AttemptMirrorState:
    """Terminal attempt fields needed to mirror a legacy submission."""

    id: UUID
    user_id: int
    requirement_uuid: UUID
    submission_value_kind: str
    submitted_value: str
    github_username_snapshot: str | None
    cloud_provider: str | None
    outcome: str | None
    feedback_json: list[dict] | None
    validation_message: str | None
    legacy_job_id: UUID | None


@dataclass(frozen=True, slots=True)
class ActiveAttemptRow:
    """Minimal projection of an in-flight (``outcome IS NULL``) attempt.

    Used to render the "verification in progress" card state -- replaces
    the legacy ``VerificationJob`` active-row read for that purpose.
    """

    id: UUID
    requirement_uuid: UUID


@dataclass(frozen=True, slots=True)
class AttemptCardProjection:
    """Latest terminal attempt for one requirement, for card rendering."""

    id: UUID
    requirement_uuid: UUID
    submission_value_kind: str
    submitted_value: str
    github_username_snapshot: str | None
    cloud_provider: str | None
    outcome: str
    feedback_json: list[dict] | None
    validation_message: str | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class FinalizeResult:
    """Outcome of a compare-and-set finalize.

    ``won`` is ``True`` when this call set the terminal state, ``False`` when
    the attempt was already terminal (replay / competing finalizer). ``state``
    always reflects the authoritative terminal row.
    """

    won: bool
    state: AttemptTerminalState


class AttemptAlreadyGoneError(Exception):
    """The attempt row disappeared between reads (should not happen in prod)."""


class AttemptAlreadyValidatedError(Exception):
    """A succeeded attempt already exists for this (user, requirement)."""


class VerificationAttemptRepository:
    """Data access for verification attempts.

    Most methods here run under the Functions role's narrowed column
    grants (see migration 0051). :meth:`create_or_get_active` and
    :meth:`delete_active` are the API-side submission-creation path and run
    under the API's normal (unrestricted) role instead.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_or_get_active(
        self,
        *,
        id: UUID,
        user_id: int,
        requirement_uuid: UUID,
        artifact_schema_version: int,
        curriculum_version: int,
        content_hash: str,
        requirement_snapshot: Mapping[str, object],
        requirement_snapshot_hash: str,
        payload_version: int,
        github_username_snapshot: str | None,
        submitted_value: SubmittedValue,
        cloud_provider: str | None,
        traceparent: str | None,
        legacy_job_id: UUID | None,
    ) -> tuple[VerificationAttempt, bool]:
        """Create a new attempt, or return the active one, under an advisory lock.

        Takes a transaction-scoped advisory lock keyed on ``(user_id,
        requirement_uuid)`` before checking anything, so two concurrent
        submits for the same requirement can never interleave their reads
        and writes. With the lock held, this rechecks both an existing
        *succeeded* attempt (closing the race between a concurrent
        successful finalization and a new submit) and an existing *active*
        attempt (the one-active-attempt invariant) before inserting a
        brand-new row. The lock releases automatically when the caller
        commits or rolls back the transaction.
        """
        await self._acquire_submission_lock(user_id, requirement_uuid)

        succeeded = await self.db.execute(
            select(VerificationAttempt.id)
            .where(
                VerificationAttempt.user_id == user_id,
                VerificationAttempt.requirement_uuid == requirement_uuid,
                VerificationAttempt.outcome
                == VerificationAttemptOutcome.SUCCEEDED.value,
            )
            .limit(1)
        )
        if succeeded.scalar_one_or_none() is not None:
            raise AttemptAlreadyValidatedError(
                f"user {user_id} already has a succeeded attempt for "
                f"requirement {requirement_uuid}"
            )

        active = await self.db.execute(
            select(VerificationAttempt)
            .where(
                VerificationAttempt.user_id == user_id,
                VerificationAttempt.requirement_uuid == requirement_uuid,
                VerificationAttempt.outcome.is_(None),
            )
            .limit(1)
        )
        existing = active.scalar_one_or_none()
        if existing is not None:
            return existing, False

        attempt = VerificationAttempt(
            id=id,
            user_id=user_id,
            requirement_uuid=requirement_uuid,
            artifact_schema_version=artifact_schema_version,
            curriculum_version=curriculum_version,
            content_hash=content_hash,
            requirement_snapshot=dict(requirement_snapshot),
            requirement_snapshot_hash=requirement_snapshot_hash,
            snapshot_source=VerificationSnapshotSource.SUBMITTED.value,
            payload_version=payload_version,
            github_username_snapshot=github_username_snapshot,
            cloud_provider=cloud_provider,
            traceparent=traceparent,
            legacy_job_id=legacy_job_id,
            submission_value_kind=submitted_value.kind.value,
            submitted_value=submitted_value.as_text,
        )
        self.db.add(attempt)
        await self.db.flush()
        return attempt, True

    async def delete_active(self, attempt_id: UUID) -> bool:
        """Delete an attempt that never started, freeing its active slot.

        Used only when the API's own Durable start call fails before
        reaching Functions (a config error, or a transport error before the
        request landed) -- the attempt never ran, so nothing about it is
        worth retaining. The lifecycle guards preserve rows already claimed
        by Functions or terminalized by an authoritative writer.
        """
        stmt = delete(VerificationAttempt).where(
            VerificationAttempt.id == attempt_id,
            VerificationAttempt.outcome.is_(None),
            VerificationAttempt.started_at.is_(None),
        )
        result = await self.db.execute(stmt)
        return (getattr(result, "rowcount", 0) or 0) > 0

    async def _acquire_submission_lock(
        self, user_id: int, requirement_uuid: UUID
    ) -> None:
        """Take a transaction-scoped advisory lock for one (user, requirement).

        ``hashtextextended`` folds the composite key into the single
        64-bit value ``pg_advisory_xact_lock`` takes, so the lock target is
        deterministic and collision-resistant without a second, session-level
        unlock call to remember -- Postgres releases a ``_xact_lock``
        automatically at commit or rollback.
        """
        lock_key = f"verification_attempt:{user_id}:{requirement_uuid}"
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": lock_key},
        )

    async def get_prepare_state(self, attempt_id: UUID) -> AttemptPrepareState | None:
        """Load the identity + submitted snapshot for one attempt."""
        result = await self.db.execute(
            select(
                VerificationAttempt.id,
                VerificationAttempt.user_id,
                VerificationAttempt.requirement_uuid,
                VerificationAttempt.snapshot_source,
                VerificationAttempt.payload_version,
                VerificationAttempt.requirement_snapshot,
                VerificationAttempt.requirement_snapshot_hash,
                VerificationAttempt.submission_value_kind,
                VerificationAttempt.submitted_value,
                VerificationAttempt.github_username_snapshot,
                VerificationAttempt.cloud_provider,
                VerificationAttempt.traceparent,
                VerificationAttempt.outcome,
                VerificationAttempt.started_at,
                VerificationAttempt.legacy_job_id,
            ).where(VerificationAttempt.id == attempt_id)
        )
        row = result.one_or_none()
        if row is None:
            return None
        return AttemptPrepareState(
            id=row.id,
            user_id=row.user_id,
            requirement_uuid=row.requirement_uuid,
            snapshot_source=row.snapshot_source,
            payload_version=row.payload_version,
            requirement_snapshot=row.requirement_snapshot,
            requirement_snapshot_hash=row.requirement_snapshot_hash,
            submission_value_kind=row.submission_value_kind,
            submitted_value=row.submitted_value,
            github_username_snapshot=row.github_username_snapshot,
            cloud_provider=row.cloud_provider,
            traceparent=row.traceparent,
            outcome=row.outcome,
            started_at=row.started_at,
            legacy_job_id=row.legacy_job_id,
        )

    async def mark_started(
        self, attempt_id: UUID, *, started_at: datetime | None = None
    ) -> bool:
        """Record when an active attempt begins execution."""
        now = started_at or utcnow()
        result = await self.db.execute(
            update(VerificationAttempt)
            .where(
                VerificationAttempt.id == attempt_id,
                VerificationAttempt.outcome.is_(None),
                VerificationAttempt.started_at.is_(None),
            )
            .values(started_at=now, updated_at=now)
            .returning(VerificationAttempt.id)
        )
        return result.scalar_one_or_none() is not None

    async def get_status(self, attempt_id: UUID) -> AttemptStatusRow | None:
        """Load the lifecycle projection for one attempt."""
        result = await self.db.execute(
            select(
                VerificationAttempt.id,
                VerificationAttempt.user_id,
                VerificationAttempt.requirement_uuid,
                VerificationAttempt.outcome,
                VerificationAttempt.started_at,
                VerificationAttempt.created_at,
                VerificationAttempt.legacy_job_id,
            ).where(VerificationAttempt.id == attempt_id)
        )
        row = result.one_or_none()
        if row is None:
            return None
        return AttemptStatusRow(
            id=row.id,
            user_id=row.user_id,
            requirement_uuid=row.requirement_uuid,
            outcome=row.outcome,
            started_at=row.started_at,
            created_at=row.created_at,
            legacy_job_id=row.legacy_job_id,
        )

    async def get_terminal_state(self, attempt_id: UUID) -> AttemptTerminalState | None:
        """Load the terminal projection for one attempt."""
        result = await self.db.execute(
            select(
                VerificationAttempt.id,
                VerificationAttempt.outcome,
                VerificationAttempt.error_code,
                VerificationAttempt.validation_message,
                VerificationAttempt.terminal_source,
                VerificationAttempt.completed_at,
            ).where(VerificationAttempt.id == attempt_id)
        )
        row = result.one_or_none()
        if row is None:
            return None
        return AttemptTerminalState(
            id=row.id,
            outcome=row.outcome,
            error_code=row.error_code,
            validation_message=row.validation_message,
            terminal_source=row.terminal_source,
            completed_at=row.completed_at,
        )

    async def get_mirror_state(self, attempt_id: UUID) -> AttemptMirrorState | None:
        """Load the terminal fields needed to mirror a legacy submission."""
        result = await self.db.execute(
            select(
                VerificationAttempt.id,
                VerificationAttempt.user_id,
                VerificationAttempt.requirement_uuid,
                VerificationAttempt.submission_value_kind,
                VerificationAttempt.submitted_value,
                VerificationAttempt.github_username_snapshot,
                VerificationAttempt.cloud_provider,
                VerificationAttempt.outcome,
                VerificationAttempt.feedback_json,
                VerificationAttempt.validation_message,
                VerificationAttempt.legacy_job_id,
            ).where(VerificationAttempt.id == attempt_id)
        )
        row = result.one_or_none()
        if row is None:
            return None
        return AttemptMirrorState(
            id=row.id,
            user_id=row.user_id,
            requirement_uuid=row.requirement_uuid,
            submission_value_kind=row.submission_value_kind,
            submitted_value=row.submitted_value,
            github_username_snapshot=row.github_username_snapshot,
            cloud_provider=row.cloud_provider,
            outcome=row.outcome,
            feedback_json=row.feedback_json,
            validation_message=row.validation_message,
            legacy_job_id=row.legacy_job_id,
        )

    async def list_active_older_than(
        self, cutoff: datetime, *, limit: int
    ) -> list[AttemptStatusRow]:
        """Return active (``outcome IS NULL``) attempts created before ``cutoff``.

        Ordered oldest-first and bounded by ``limit`` so a reconciler pass
        drains the backlog deterministically without unbounded work.
        """
        result = await self.db.execute(
            select(
                VerificationAttempt.id,
                VerificationAttempt.user_id,
                VerificationAttempt.requirement_uuid,
                VerificationAttempt.outcome,
                VerificationAttempt.started_at,
                VerificationAttempt.created_at,
                VerificationAttempt.legacy_job_id,
            )
            .where(
                VerificationAttempt.outcome.is_(None),
                func.coalesce(
                    VerificationAttempt.started_at,
                    VerificationAttempt.created_at,
                )
                < cutoff,
            )
            .order_by(
                func.coalesce(
                    VerificationAttempt.started_at,
                    VerificationAttempt.created_at,
                ).asc()
            )
            .limit(limit)
        )
        return [
            AttemptStatusRow(
                id=row.id,
                user_id=row.user_id,
                requirement_uuid=row.requirement_uuid,
                outcome=row.outcome,
                started_at=row.started_at,
                created_at=row.created_at,
                legacy_job_id=row.legacy_job_id,
            )
            for row in result.all()
        ]

    async def finalize(
        self,
        attempt_id: UUID,
        *,
        outcome: VerificationAttemptOutcome | str,
        error_code: str | None,
        validation_message: str | None,
        terminal_source: str,
        feedback_json: list[dict] | None,
        completed_at: datetime | None = None,
    ) -> FinalizeResult:
        """Compare-and-set an attempt to a terminal outcome.

        Only writes when ``outcome IS NULL``. On a lost CAS (already terminal),
        reloads and returns the authoritative terminal state without mutating
        it, so replays and competing finalizers never clobber a result.
        """
        normalized_outcome = (
            outcome.value
            if isinstance(outcome, VerificationAttemptOutcome)
            else VerificationAttemptOutcome(outcome).value
        )
        now = completed_at or utcnow()
        stmt = (
            update(VerificationAttempt)
            .where(
                VerificationAttempt.id == attempt_id,
                VerificationAttempt.outcome.is_(None),
            )
            .values(
                outcome=normalized_outcome,
                error_code=error_code,
                validation_message=validation_message,
                terminal_source=terminal_source,
                feedback_json=feedback_json,
                completed_at=now,
                updated_at=now,
            )
            .returning(
                VerificationAttempt.id,
                VerificationAttempt.outcome,
                VerificationAttempt.error_code,
                VerificationAttempt.validation_message,
                VerificationAttempt.terminal_source,
                VerificationAttempt.completed_at,
            )
        )
        result = await self.db.execute(stmt)
        row = result.one_or_none()
        if row is not None:
            return FinalizeResult(
                won=True,
                state=AttemptTerminalState(
                    id=row.id,
                    outcome=row.outcome,
                    error_code=row.error_code,
                    validation_message=row.validation_message,
                    terminal_source=row.terminal_source,
                    completed_at=row.completed_at,
                ),
            )

        existing = await self.get_terminal_state(attempt_id)
        if existing is None:
            raise AttemptAlreadyGoneError(str(attempt_id))
        return FinalizeResult(won=False, state=existing)

    # Authoritative progress, gating, card, and stats reads.

    async def get_succeeded_requirement_uuids(self, user_id: int) -> set[UUID]:
        """Return every requirement UUID with at least one succeeded attempt.

        Mirrors ``SubmissionRepository.get_validated_requirement_uuids``
        against the authoritative table; callers intersect the result with
        the catalog's current requirement UUIDs.
        """
        result = await self.db.execute(
            select(func.distinct(VerificationAttempt.requirement_uuid)).where(
                VerificationAttempt.user_id == user_id,
                VerificationAttempt.outcome
                == VerificationAttemptOutcome.SUCCEEDED.value,
            )
        )
        return set(result.scalars().all())

    async def count_succeeded_for_requirements(
        self, user_id: int, requirement_uuids: Iterable[UUID]
    ) -> int:
        """Count how many of the given requirement UUIDs have succeeded.

        Filters against a specific set of UUIDs (from current content) so a
        retired requirement never inflates the count.
        """
        uuids = list(requirement_uuids)
        if not uuids:
            return 0
        result = await self.db.execute(
            select(
                func.count(func.distinct(VerificationAttempt.requirement_uuid))
            ).where(
                VerificationAttempt.user_id == user_id,
                VerificationAttempt.requirement_uuid.in_(uuids),
                VerificationAttempt.outcome
                == VerificationAttemptOutcome.SUCCEEDED.value,
            )
        )
        return result.scalar_one() or 0

    async def are_all_requirements_succeeded(
        self, user_id: int, requirement_uuids: Iterable[UUID]
    ) -> bool:
        """Check if the user has a succeeded attempt for ALL given requirements.

        Used for sequential phase gating -- ensures prior-phase verification
        is fully complete before allowing the next phase's submissions.
        """
        uuids = list(requirement_uuids)
        if not uuids:
            return True
        succeeded = await self.count_succeeded_for_requirements(user_id, uuids)
        return succeeded >= len(uuids)

    async def get_requirement_uuids_with_any_attempt(
        self, user_id: int, requirement_uuids: Iterable[UUID]
    ) -> set[UUID]:
        """Requirement UUIDs that already have at least one attempt row.

        An authoritative attempt -- active or terminal -- always wins over
        legacy data, so callers use this to scope the legacy submission-card
        fallback to only the requirements with zero attempt history at all.
        """
        uuids = list(requirement_uuids)
        if not uuids:
            return set()
        result = await self.db.execute(
            select(func.distinct(VerificationAttempt.requirement_uuid)).where(
                VerificationAttempt.user_id == user_id,
                VerificationAttempt.requirement_uuid.in_(uuids),
            )
        )
        return set(result.scalars().all())

    async def get_active_for_requirements(
        self, user_id: int, requirement_uuids: Iterable[UUID]
    ) -> list[ActiveAttemptRow]:
        """Get active (``outcome IS NULL``) attempts across a set of requirements.

        Replaces the legacy ``VerificationJobRepository.get_active_for_requirements``
        read for the phase page's "verification in progress" indicator --
        ``VerificationAttempt.id`` is the same UUID used as the Durable
        instance id and the status-token job id.
        """
        uuids = list(requirement_uuids)
        if not uuids:
            return []
        result = await self.db.execute(
            select(VerificationAttempt.id, VerificationAttempt.requirement_uuid).where(
                VerificationAttempt.user_id == user_id,
                VerificationAttempt.requirement_uuid.in_(uuids),
                VerificationAttempt.outcome.is_(None),
            )
        )
        return [
            ActiveAttemptRow(id=row.id, requirement_uuid=row.requirement_uuid)
            for row in result.all()
        ]

    async def get_latest_terminal_for_requirements(
        self, user_id: int, requirement_uuids: Iterable[UUID]
    ) -> list[AttemptCardProjection]:
        """Get the latest *terminal* attempt per requirement_uuid for a user.

        Active attempts are deliberately excluded -- the phase page renders
        those separately as the "in progress" spinner state (see
        :meth:`get_active_for_requirements`); this feeds the requirement
        card's persisted result (succeeded/failed/server_error/cancelled)
        shown alongside or instead of that spinner.
        """
        uuids = list(requirement_uuids)
        if not uuids:
            return []

        latest_sq = (
            select(
                VerificationAttempt.requirement_uuid,
                func.max(VerificationAttempt.created_at).label("max_created_at"),
            )
            .where(
                VerificationAttempt.user_id == user_id,
                VerificationAttempt.requirement_uuid.in_(uuids),
                VerificationAttempt.outcome.is_not(None),
            )
            .group_by(VerificationAttempt.requirement_uuid)
            .subquery()
        )
        result = await self.db.execute(
            select(
                VerificationAttempt.id,
                VerificationAttempt.requirement_uuid,
                VerificationAttempt.submission_value_kind,
                VerificationAttempt.submitted_value,
                VerificationAttempt.github_username_snapshot,
                VerificationAttempt.cloud_provider,
                VerificationAttempt.outcome,
                VerificationAttempt.feedback_json,
                VerificationAttempt.validation_message,
                VerificationAttempt.completed_at,
                VerificationAttempt.created_at,
                VerificationAttempt.updated_at,
            )
            .join(
                latest_sq,
                and_(
                    VerificationAttempt.requirement_uuid
                    == latest_sq.c.requirement_uuid,
                    VerificationAttempt.created_at == latest_sq.c.max_created_at,
                ),
            )
            .where(VerificationAttempt.user_id == user_id)
        )
        return [
            AttemptCardProjection(
                id=row.id,
                requirement_uuid=row.requirement_uuid,
                submission_value_kind=row.submission_value_kind,
                submitted_value=row.submitted_value,
                github_username_snapshot=row.github_username_snapshot,
                cloud_provider=row.cloud_provider,
                outcome=row.outcome,
                feedback_json=row.feedback_json,
                validation_message=row.validation_message,
                completed_at=row.completed_at,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in result.all()
        ]

    async def list_phase_completions(
        self,
        requirement_counts_by_phase: dict[int, int],
        phase_order_by_requirement_uuid: Mapping[UUID, int],
    ) -> list[tuple[int, int]]:
        """List ``(phase_order, user_id)`` for fully phase-verified users.

        Mirrors ``SubmissionRepository.list_phase_completions`` (see that
        docstring for the ``VALUES``-relation shape that avoids a
        curriculum-table join) but sources succeeded ``verification_attempts``
        as the primary signal. Also folds in legacy ``submissions.is_validated``
        rows via a single ``UNION`` -- a narrow safety net only when the
        (user, requirement) pair has no attempt row at all. Reconciliation is
        expected to have already run before this reader is enabled, so this is
        a fallback for the rare gap, not the primary path.
        """
        completable = {
            order: total
            for order, total in requirement_counts_by_phase.items()
            if total > 0
        }
        if not completable:
            return []

        requirement_phase_rows = [
            (req_uuid, order)
            for req_uuid, order in phase_order_by_requirement_uuid.items()
            if order in completable
        ]
        if not requirement_phase_rows:
            return []

        requirement_phase_map = values(
            column("requirement_uuid", Uuid(as_uuid=True)),
            column("phase_order", Integer),
            name="requirement_phase_map",
        ).data(requirement_phase_rows)

        succeeded_attempts = select(
            VerificationAttempt.user_id,
            VerificationAttempt.requirement_uuid,
            literal(0).label("legacy_rows"),
        ).where(
            VerificationAttempt.outcome == VerificationAttemptOutcome.SUCCEEDED.value
        )
        validated_legacy = select(
            Submission.user_id,
            Submission.requirement_uuid,
            literal(1).label("legacy_rows"),
        ).where(
            Submission.is_validated.is_(True),
            ~exists().where(
                VerificationAttempt.user_id == Submission.user_id,
                VerificationAttempt.requirement_uuid == Submission.requirement_uuid,
            ),
        )
        succeeded = union_all(succeeded_attempts, validated_legacy).subquery(
            "succeeded"
        )

        result = await self.db.execute(
            select(
                requirement_phase_map.c.phase_order,
                succeeded.c.user_id,
                func.count(func.distinct(succeeded.c.requirement_uuid)).label(
                    "validated"
                ),
                func.sum(succeeded.c.legacy_rows).label("legacy_rows"),
            )
            .select_from(succeeded)
            .join(
                requirement_phase_map,
                succeeded.c.requirement_uuid
                == requirement_phase_map.c.requirement_uuid,
            )
            .group_by(requirement_phase_map.c.phase_order, succeeded.c.user_id)
        )
        rows = result.all()
        legacy_rows = sum(row.legacy_rows or 0 for row in rows)
        if legacy_rows:
            logger.warning(
                "stats.legacy_fallback_used",
                extra={"count": legacy_rows},
            )
        return [
            (row.phase_order, row.user_id)
            for row in rows
            if row.validated >= completable[row.phase_order]
        ]
