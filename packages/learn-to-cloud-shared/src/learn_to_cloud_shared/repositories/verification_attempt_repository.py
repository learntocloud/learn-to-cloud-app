"""Repository for verification attempts and compare-and-set finalization."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Integer,
    Uuid,
    and_,
    column,
    func,
    literal,
    or_,
    select,
    text,
    union_all,
    update,
    values,
)
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.models import (
    VerificationAttempt,
    VerificationAttemptOutcome,
    VerificationSnapshotSource,
    utcnow,
)
from learn_to_cloud_shared.submission_values import SubmittedValue


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
    outcome: str | None
    started_at: datetime | None


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


@dataclass(frozen=True, slots=True)
class ActiveAttemptRow:
    """Minimal projection of an in-flight attempt."""

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
class AttemptHistoryProjection:
    """Terminal attempt fields safe for learner history rendering."""

    id: UUID
    requirement_uuid: UUID
    submission_value_kind: str
    submitted_value: str
    outcome: str
    feedback_json: list[dict] | None
    validation_message: str | None
    completed_at: datetime | None
    created_at: datetime


def _to_history_projection(row: Row[Any]) -> AttemptHistoryProjection:
    return AttemptHistoryProjection(
        id=row.id,
        requirement_uuid=row.requirement_uuid,
        submission_value_kind=row.submission_value_kind,
        submitted_value=row.submitted_value,
        outcome=row.outcome,
        feedback_json=row.feedback_json,
        validation_message=row.validation_message,
        completed_at=row.completed_at,
        created_at=row.created_at,
    )


@dataclass(frozen=True, slots=True)
class FinalizeResult:
    """Outcome of a compare-and-set finalize.

    ``won`` is ``True`` when this call set the terminal state, ``False`` when
    the attempt was already terminal (replay / competing finalizer). ``state``
    always reflects the authoritative terminal row.
    """

    won: bool
    state: AttemptTerminalState


@dataclass(frozen=True, slots=True)
class CommunityActivityRow:
    """Aggregate verification activity for the community page."""

    phase_order: int | None
    active_learners: int
    attempts: int
    projects_verified: int


class AttemptAlreadyGoneError(Exception):
    """The attempt row disappeared between reads (should not happen in prod)."""


class AttemptAlreadyValidatedError(Exception):
    """A succeeded attempt already exists for this (user, requirement)."""


class VerificationAttemptRepository:
    """Data access for verification attempts.

    Most methods here run under the Functions role's narrowed column grants
    (see migration 0051). :meth:`create_or_get_active` is the API-side
    submission-creation path and runs under the API's normal role instead.
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
            submission_value_kind=submitted_value.kind.value,
            submitted_value=submitted_value.as_text,
        )
        self.db.add(attempt)
        await self.db.flush()
        return attempt, True

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
                VerificationAttempt.outcome,
                VerificationAttempt.started_at,
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
            outcome=row.outcome,
            started_at=row.started_at,
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

    async def finalize_unstarted(
        self,
        attempt_id: UUID,
        *,
        outcome: VerificationAttemptOutcome | str,
        error_code: str,
        validation_message: str,
        terminal_source: str,
        completed_at: datetime | None = None,
    ) -> FinalizeResult | None:
        """Finalize only while an attempt is both active and unclaimed."""
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
                VerificationAttempt.started_at.is_(None),
            )
            .values(
                outcome=normalized_outcome,
                error_code=error_code,
                validation_message=validation_message,
                terminal_source=terminal_source,
                feedback_json=None,
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

        existing = await self.get_status(attempt_id)
        if existing is None:
            raise AttemptAlreadyGoneError(str(attempt_id))
        if existing.outcome is None:
            return None
        terminal = await self.get_terminal_state(attempt_id)
        if terminal is None:
            raise AttemptAlreadyGoneError(str(attempt_id))
        return FinalizeResult(won=False, state=terminal)

    # Authoritative progress, gating, card, and stats reads.

    async def get_succeeded_requirement_uuids(self, user_id: int) -> set[UUID]:
        """Return every requirement UUID with at least one succeeded attempt.

        Callers intersect the result with current catalog requirement UUIDs.
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

    async def get_active_for_requirements(
        self, user_id: int, requirement_uuids: Iterable[UUID]
    ) -> list[ActiveAttemptRow]:
        """Get active (``outcome IS NULL``) attempts across a set of requirements.

        ``VerificationAttempt.id`` is also the Durable instance id and the
        status-token attempt id.
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

        ranked_sq = (
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
                func.row_number()
                .over(
                    partition_by=VerificationAttempt.requirement_uuid,
                    order_by=(
                        VerificationAttempt.created_at.desc(),
                        VerificationAttempt.id.desc(),
                    ),
                )
                .label("row_number"),
            )
            .where(
                VerificationAttempt.user_id == user_id,
                VerificationAttempt.requirement_uuid.in_(uuids),
                VerificationAttempt.outcome.is_not(None),
            )
            .subquery()
        )
        result = await self.db.execute(
            select(
                ranked_sq.c.id,
                ranked_sq.c.requirement_uuid,
                ranked_sq.c.submission_value_kind,
                ranked_sq.c.submitted_value,
                ranked_sq.c.github_username_snapshot,
                ranked_sq.c.cloud_provider,
                ranked_sq.c.outcome,
                ranked_sq.c.feedback_json,
                ranked_sq.c.validation_message,
                ranked_sq.c.completed_at,
                ranked_sq.c.created_at,
                ranked_sq.c.updated_at,
            ).where(ranked_sq.c.row_number == 1)
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

    async def get_terminal_history_for_requirements(
        self,
        user_id: int,
        requirement_uuids: Iterable[UUID],
        *,
        per_requirement_limit: int,
    ) -> list[AttemptHistoryProjection]:
        """Return each requirement's newest terminal attempts in one query."""
        uuids = list(requirement_uuids)
        if not uuids or per_requirement_limit <= 0:
            return []

        ranked_sq = (
            select(
                VerificationAttempt.id,
                VerificationAttempt.requirement_uuid,
                VerificationAttempt.submission_value_kind,
                VerificationAttempt.submitted_value,
                VerificationAttempt.outcome,
                VerificationAttempt.feedback_json,
                VerificationAttempt.validation_message,
                VerificationAttempt.completed_at,
                VerificationAttempt.created_at,
                func.row_number()
                .over(
                    partition_by=VerificationAttempt.requirement_uuid,
                    order_by=(
                        VerificationAttempt.created_at.desc(),
                        VerificationAttempt.id.desc(),
                    ),
                )
                .label("row_number"),
            )
            .where(
                VerificationAttempt.user_id == user_id,
                VerificationAttempt.requirement_uuid.in_(uuids),
                VerificationAttempt.outcome.is_not(None),
            )
            .subquery()
        )
        result = await self.db.execute(
            select(
                ranked_sq.c.id,
                ranked_sq.c.requirement_uuid,
                ranked_sq.c.submission_value_kind,
                ranked_sq.c.submitted_value,
                ranked_sq.c.outcome,
                ranked_sq.c.feedback_json,
                ranked_sq.c.validation_message,
                ranked_sq.c.completed_at,
                ranked_sq.c.created_at,
            )
            .where(ranked_sq.c.row_number <= per_requirement_limit)
            .order_by(
                ranked_sq.c.requirement_uuid,
                ranked_sq.c.created_at.desc(),
                ranked_sq.c.id.desc(),
            )
        )
        return [_to_history_projection(row) for row in result.all()]

    async def get_terminal_history(
        self,
        user_id: int,
        requirement_uuid: UUID,
        *,
        limit: int,
        before: tuple[datetime, UUID] | None = None,
    ) -> list[AttemptHistoryProjection]:
        """Return one cursor page of terminal attempts, newest first."""
        if limit <= 0:
            return []

        query = select(
            VerificationAttempt.id,
            VerificationAttempt.requirement_uuid,
            VerificationAttempt.submission_value_kind,
            VerificationAttempt.submitted_value,
            VerificationAttempt.outcome,
            VerificationAttempt.feedback_json,
            VerificationAttempt.validation_message,
            VerificationAttempt.completed_at,
            VerificationAttempt.created_at,
        ).where(
            VerificationAttempt.user_id == user_id,
            VerificationAttempt.requirement_uuid == requirement_uuid,
            VerificationAttempt.outcome.is_not(None),
        )
        if before is not None:
            created_at, attempt_id = before
            query = query.where(
                or_(
                    VerificationAttempt.created_at < created_at,
                    and_(
                        VerificationAttempt.created_at == created_at,
                        VerificationAttempt.id < attempt_id,
                    ),
                )
            )

        result = await self.db.execute(
            query.order_by(
                VerificationAttempt.created_at.desc(),
                VerificationAttempt.id.desc(),
            ).limit(limit)
        )
        return [_to_history_projection(row) for row in result.all()]

    async def list_phase_completions(
        self,
        requirement_counts_by_phase: dict[int, int],
        phase_order_by_requirement_uuid: Mapping[UUID, int],
    ) -> list[tuple[int, int]]:
        """List ``(phase_order, user_id)`` for fully phase-verified users.

        Uses an in-query ``VALUES`` relation to map current requirement UUIDs
        to phases without joining database curriculum tables.
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
        ).where(
            VerificationAttempt.outcome == VerificationAttemptOutcome.SUCCEEDED.value
        )
        succeeded = succeeded_attempts.subquery("succeeded")

        result = await self.db.execute(
            select(
                requirement_phase_map.c.phase_order,
                succeeded.c.user_id,
                func.count(func.distinct(succeeded.c.requirement_uuid)).label(
                    "validated"
                ),
            )
            .select_from(succeeded)
            .join(
                requirement_phase_map,
                succeeded.c.requirement_uuid
                == requirement_phase_map.c.requirement_uuid,
            )
            .group_by(requirement_phase_map.c.phase_order, succeeded.c.user_id)
        )
        return [
            (row.phase_order, row.user_id)
            for row in result.all()
            if row.validated >= completable[row.phase_order]
        ]

    async def get_community_activity(
        self,
        *,
        since: datetime,
        phase_order_by_requirement_uuid: Mapping[UUID, int],
    ) -> list[CommunityActivityRow]:
        """Aggregate recent attempts and verified projects by current phase."""
        requirement_phase_rows = list(
            phase_order_by_requirement_uuid.items(),
        )
        if not requirement_phase_rows:
            return []

        requirement_phase_map = values(
            column("requirement_uuid", Uuid(as_uuid=True)),
            column("phase_order", Integer),
            name="community_requirement_phase_map",
        ).data(requirement_phase_rows)
        mapped_attempts = (
            select(
                requirement_phase_map.c.phase_order,
                VerificationAttempt.user_id,
                VerificationAttempt.requirement_uuid,
                VerificationAttempt.outcome,
                VerificationAttempt.created_at,
                VerificationAttempt.completed_at,
            )
            .select_from(VerificationAttempt)
            .join(
                requirement_phase_map,
                VerificationAttempt.requirement_uuid
                == requirement_phase_map.c.requirement_uuid,
            )
            .subquery("mapped_attempts")
        )
        recent_attempts = (
            mapped_attempts.select()
            .where(
                mapped_attempts.c.created_at >= since,
            )
            .subquery("recent_attempts")
        )
        recent_verified_projects = (
            select(
                mapped_attempts.c.phase_order,
                mapped_attempts.c.user_id,
                mapped_attempts.c.requirement_uuid,
            )
            .where(
                mapped_attempts.c.outcome == VerificationAttemptOutcome.SUCCEEDED.value,
                mapped_attempts.c.completed_at >= since,
            )
            .distinct()
            .subquery("recent_verified_projects")
        )
        zero = literal(0, type_=Integer)
        total_phase_order = literal(None, type_=Integer)
        activity_rows = union_all(
            select(
                total_phase_order.label("phase_order"),
                func.count(func.distinct(recent_attempts.c.user_id)).label(
                    "active_learners"
                ),
                func.count().label("attempts"),
                zero.label("projects_verified"),
            ),
            select(
                recent_attempts.c.phase_order,
                func.count(func.distinct(recent_attempts.c.user_id)).label(
                    "active_learners"
                ),
                func.count().label("attempts"),
                zero.label("projects_verified"),
            ).group_by(recent_attempts.c.phase_order),
            select(
                total_phase_order.label("phase_order"),
                zero.label("active_learners"),
                zero.label("attempts"),
                func.count().label("projects_verified"),
            ).select_from(recent_verified_projects),
            select(
                recent_verified_projects.c.phase_order,
                zero.label("active_learners"),
                zero.label("attempts"),
                func.count().label("projects_verified"),
            ).group_by(recent_verified_projects.c.phase_order),
        ).subquery("community_activity_rows")
        result = await self.db.execute(
            select(
                activity_rows.c.phase_order,
                func.sum(activity_rows.c.active_learners).label("active_learners"),
                func.sum(activity_rows.c.attempts).label("attempts"),
                func.sum(activity_rows.c.projects_verified).label("projects_verified"),
            )
            .group_by(activity_rows.c.phase_order)
            .order_by(activity_rows.c.phase_order)
        )
        return [
            CommunityActivityRow(
                phase_order=row.phase_order,
                active_learners=int(row.active_learners),
                attempts=int(row.attempts),
                projects_verified=int(row.projects_verified),
            )
            for row in result.all()
        ]
