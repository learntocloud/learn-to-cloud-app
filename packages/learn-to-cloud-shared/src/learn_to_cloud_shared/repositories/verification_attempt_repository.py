"""Repository for the unified ``verification_attempts`` table.

The bridge (PR4) reads and finalizes attempts here. Every write to a
terminal state goes through :meth:`VerificationAttemptRepository.finalize`,
which is a compare-and-set (``UPDATE ... WHERE id=:id AND outcome IS NULL
RETURNING``) so a Durable replay, a competing finalizer, and the stale-attempt
reconciler can never overwrite a result that is already terminal.

Reads are deliberately narrow: prepare/reconcile only select the columns the
Functions role is granted, matching the column-level privileges the bridge
migration installs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.models import (
    VerificationAttempt,
    VerificationAttemptOutcome,
    utcnow,
)


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


class VerificationAttemptRepository:
    """Data access for verification attempts, scoped to the Functions role."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

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
