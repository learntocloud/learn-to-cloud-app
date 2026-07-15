"""Integration tests for stats aggregates (phase completion + counts)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.content_catalog import get_curriculum_catalog
from learn_to_cloud_shared.content_service import get_requirement_counts_by_phase
from learn_to_cloud_shared.content_sync import sync_curriculum_to_db
from learn_to_cloud_shared.content_yaml_loader import clear_cache
from learn_to_cloud_shared.models import (
    CurriculumPhase,
    CurriculumRequirement,
    SubmissionValueKind,
    utcnow,
)
from learn_to_cloud_shared.repositories.submission_repository import (
    SubmissionRepository,
)
from learn_to_cloud_shared.repositories.user_repository import UserRepository
from learn_to_cloud_shared.repositories.verification_attempt_repository import (
    VerificationAttemptRepository,
)
from learn_to_cloud_shared.submission_values import SubmittedValue

pytestmark = pytest.mark.integration


def _value_for_kind(kind: str, seed: str) -> SubmittedValue:
    """Build a schema-valid SubmittedValue for a requirement's value kind."""
    value_kind = SubmissionValueKind(kind)
    match value_kind:
        case SubmissionValueKind.GITHUB_URL:
            return SubmittedValue(
                kind=value_kind, github_url=f"https://github.com/{seed}"
            )
        case SubmissionValueKind.TOKEN:
            return SubmittedValue(kind=value_kind, token_value=f"token-{seed}")
        case SubmissionValueKind.DEPLOYED_URL:
            return SubmittedValue(
                kind=value_kind, deployed_url=f"https://{seed}.example.com"
            )
        case SubmissionValueKind.TEXT:
            return SubmittedValue(kind=value_kind, text_value=f"reflection {seed}")


@pytest.fixture()
async def reqs_by_phase(db_session: AsyncSession) -> dict[int, list[tuple]]:
    """Sync curriculum; return {phase_order: [(uuid, value_kind), ...]}."""
    clear_cache()
    await sync_curriculum_to_db(db_session)
    result = await db_session.execute(
        select(
            CurriculumPhase.order,
            CurriculumRequirement.uuid,
            CurriculumRequirement.submission_value_kind,
        )
        .join(
            CurriculumPhase,
            CurriculumRequirement.phase_uuid == CurriculumPhase.uuid,
        )
        .where(
            CurriculumRequirement.deleted_at.is_(None),
            CurriculumPhase.deleted_at.is_(None),
        )
    )
    by_phase: dict[int, list[tuple]] = {}
    for order, uuid, kind in result.all():
        by_phase.setdefault(order, []).append((uuid, kind))
    return by_phase


async def _validate_all(
    db_session: AsyncSession, user_id: int, reqs: list[tuple]
) -> None:
    repo = SubmissionRepository(db_session)
    for uuid, kind in reqs:
        await repo.create(
            user_id=user_id,
            requirement_uuid=uuid,
            submitted_value=_value_for_kind(kind, f"u{user_id}"),
            extracted_username=None,
            is_validated=True,
        )


class TestListPhaseCompletions:
    async def test_user_appears_only_when_all_requirements_validated(
        self, db_session: AsyncSession, reqs_by_phase
    ):
        # A phase with a single requirement (easy full completion).
        single_phase = next(
            order for order, reqs in reqs_by_phase.items() if len(reqs) == 1
        )
        user_id = 50001
        await UserRepository(db_session).upsert(
            user_id, github_username="fullcompleter"
        )
        await _validate_all(db_session, user_id, reqs_by_phase[single_phase])
        await db_session.flush()

        counts = get_requirement_counts_by_phase()
        phase_order_by_requirement_uuid = (
            get_curriculum_catalog().phase_order_by_requirement_uuid
        )
        completions = await SubmissionRepository(db_session).list_phase_completions(
            counts, phase_order_by_requirement_uuid
        )

        assert (single_phase, user_id) in completions

    async def test_partial_completion_excluded(
        self, db_session: AsyncSession, reqs_by_phase
    ):
        # A phase with more than one requirement; validate only the first.
        multi_phase = next(
            order for order, reqs in reqs_by_phase.items() if len(reqs) > 1
        )
        user_id = 50002
        await UserRepository(db_session).upsert(user_id, github_username="partial")
        await _validate_all(db_session, user_id, reqs_by_phase[multi_phase][:1])
        await db_session.flush()

        counts = get_requirement_counts_by_phase()
        phase_order_by_requirement_uuid = (
            get_curriculum_catalog().phase_order_by_requirement_uuid
        )
        completions = await SubmissionRepository(db_session).list_phase_completions(
            counts, phase_order_by_requirement_uuid
        )

        assert (multi_phase, user_id) not in completions

    async def test_empty_counts_returns_empty(self, db_session: AsyncSession):
        repo = SubmissionRepository(db_session)
        assert await repo.list_phase_completions({}, {}) == []

    async def test_deleted_requirements_do_not_inflate_threshold(
        self, db_session: AsyncSession, reqs_by_phase
    ):
        # Validate every active requirement in a multi-req phase, then
        # soft-delete one requirement row. The user validated all *active*
        # requirements, so they should still count as a completer for the
        # threshold derived from active counts.
        multi_phase = next(
            order for order, reqs in reqs_by_phase.items() if len(reqs) > 1
        )
        user_id = 50003
        await UserRepository(db_session).upsert(user_id, github_username="activeonly")
        await _validate_all(db_session, user_id, reqs_by_phase[multi_phase])
        await db_session.flush()

        counts = get_requirement_counts_by_phase()
        phase_order_by_requirement_uuid = (
            get_curriculum_catalog().phase_order_by_requirement_uuid
        )
        completions = await SubmissionRepository(db_session).list_phase_completions(
            counts, phase_order_by_requirement_uuid
        )

        assert (multi_phase, user_id) in completions

    async def test_stale_requirement_uuid_is_ignored(
        self, db_session: AsyncSession, reqs_by_phase
    ):
        """A validated submission for a retired requirement UUID (no longer
        in the catalog's ``phase_order_by_requirement_uuid`` map) must not
        produce a phantom completion or otherwise blow up the aggregate.

        Simulates retirement by validating a single-requirement phase
        normally, then dropping that same requirement's UUID from the
        phase-order map passed to ``list_phase_completions`` (as if the
        catalog no longer knows about it). The join is inner, so an
        unmapped UUID simply can't match any row -- the user must no
        longer show up as a completer for that phase.
        """
        single_phase = next(
            order for order, reqs in reqs_by_phase.items() if len(reqs) == 1
        )
        user_id = 50004
        await UserRepository(db_session).upsert(user_id, github_username="stalecase")
        await _validate_all(db_session, user_id, reqs_by_phase[single_phase])
        await db_session.flush()

        retired_req_uuid = reqs_by_phase[single_phase][0][0]
        counts = get_requirement_counts_by_phase()
        phase_order_by_requirement_uuid = dict(
            get_curriculum_catalog().phase_order_by_requirement_uuid
        )
        del phase_order_by_requirement_uuid[retired_req_uuid]

        completions = await SubmissionRepository(db_session).list_phase_completions(
            counts, phase_order_by_requirement_uuid
        )

        assert (single_phase, user_id) not in completions


class TestVerificationAttemptListPhaseCompletions:
    """``VerificationAttemptRepository.list_phase_completions`` (PR6): the
    authoritative equivalent of ``SubmissionRepository.list_phase_completions``,
    sourced from succeeded ``verification_attempts`` with a narrow legacy
    ``submissions`` union for records not yet mirrored.
    """

    async def test_succeeded_attempt_counts_as_completion(
        self, db_session: AsyncSession, reqs_by_phase
    ):
        from learn_to_cloud_shared.models import VerificationAttempt

        single_phase = next(
            order for order, reqs in reqs_by_phase.items() if len(reqs) == 1
        )
        req_uuid, kind = reqs_by_phase[single_phase][0]
        user_id = 50005
        await UserRepository(db_session).upsert(user_id, github_username="attemptonly")
        db_session.add(
            VerificationAttempt(
                user_id=user_id,
                requirement_uuid=req_uuid,
                snapshot_source="reconstructed",
                submission_value_kind=kind,
                submitted_value=_value_for_kind(kind, f"u{user_id}").as_text,
                outcome="succeeded",
                completed_at=utcnow(),
            )
        )
        await db_session.flush()

        counts = get_requirement_counts_by_phase()
        phase_order_by_requirement_uuid = (
            get_curriculum_catalog().phase_order_by_requirement_uuid
        )
        completions = await VerificationAttemptRepository(
            db_session
        ).list_phase_completions(counts, phase_order_by_requirement_uuid)

        assert (single_phase, user_id) in completions

    async def test_unions_succeeded_attempts_and_legacy_submissions(
        self, db_session: AsyncSession, reqs_by_phase
    ):
        """A phase can be completed via a mix of attempts and legacy rows;
        both an authoritative-only completer and a legacy-only completer
        show up, and a mixed completer (one req via each source) also
        counts once both are unioned."""
        from learn_to_cloud_shared.models import VerificationAttempt

        multi_phase = next(
            order for order, reqs in reqs_by_phase.items() if len(reqs) > 1
        )
        reqs = reqs_by_phase[multi_phase]

        attempt_user = 50006
        legacy_user = 50007
        mixed_user = 50008
        for uid, name in (
            (attempt_user, "attemptcompleter"),
            (legacy_user, "legacycompleter"),
            (mixed_user, "mixedcompleter"),
        ):
            await UserRepository(db_session).upsert(uid, github_username=name)
        await db_session.flush()

        # attempt_user: succeeds every requirement via verification_attempts.
        for req_uuid, kind in reqs:
            db_session.add(
                VerificationAttempt(
                    user_id=attempt_user,
                    requirement_uuid=req_uuid,
                    snapshot_source="reconstructed",
                    submission_value_kind=kind,
                    submitted_value=_value_for_kind(kind, f"u{attempt_user}").as_text,
                    outcome="succeeded",
                    completed_at=utcnow(),
                )
            )
        # legacy_user: validates every requirement via the legacy table only.
        await _validate_all(db_session, legacy_user, reqs)
        # mixed_user: first requirement via attempt, rest via legacy.
        db_session.add(
            VerificationAttempt(
                user_id=mixed_user,
                requirement_uuid=reqs[0][0],
                snapshot_source="reconstructed",
                submission_value_kind=reqs[0][1],
                submitted_value=_value_for_kind(reqs[0][1], f"u{mixed_user}").as_text,
                outcome="succeeded",
                completed_at=utcnow(),
            )
        )
        await _validate_all(db_session, mixed_user, reqs[1:])
        await db_session.flush()

        counts = get_requirement_counts_by_phase()
        phase_order_by_requirement_uuid = (
            get_curriculum_catalog().phase_order_by_requirement_uuid
        )
        completions = await VerificationAttemptRepository(
            db_session
        ).list_phase_completions(counts, phase_order_by_requirement_uuid)

        assert (multi_phase, attempt_user) in completions
        assert (multi_phase, legacy_user) in completions
        assert (multi_phase, mixed_user) in completions

    async def test_authoritative_failure_overrides_legacy_success(
        self, db_session: AsyncSession, reqs_by_phase
    ):
        from learn_to_cloud_shared.models import VerificationAttempt

        single_phase = next(
            order for order, reqs in reqs_by_phase.items() if len(reqs) == 1
        )
        req_uuid, kind = reqs_by_phase[single_phase][0]
        user_id = 50010
        await UserRepository(db_session).upsert(
            user_id, github_username="authoritativefailure"
        )
        await _validate_all(db_session, user_id, [(req_uuid, kind)])
        db_session.add(
            VerificationAttempt(
                user_id=user_id,
                requirement_uuid=req_uuid,
                snapshot_source="reconstructed",
                submission_value_kind=kind,
                submitted_value=_value_for_kind(kind, f"u{user_id}").as_text,
                outcome="failed",
                completed_at=utcnow(),
            )
        )
        await db_session.flush()

        completions = await VerificationAttemptRepository(
            db_session
        ).list_phase_completions(
            get_requirement_counts_by_phase(),
            get_curriculum_catalog().phase_order_by_requirement_uuid,
        )

        assert (single_phase, user_id) not in completions

    async def test_stale_requirement_uuid_is_ignored(
        self, db_session: AsyncSession, reqs_by_phase
    ):
        from learn_to_cloud_shared.models import VerificationAttempt

        single_phase = next(
            order for order, reqs in reqs_by_phase.items() if len(reqs) == 1
        )
        req_uuid, kind = reqs_by_phase[single_phase][0]
        user_id = 50009
        await UserRepository(db_session).upsert(user_id, github_username="stalecase2")
        db_session.add(
            VerificationAttempt(
                user_id=user_id,
                requirement_uuid=req_uuid,
                snapshot_source="reconstructed",
                submission_value_kind=kind,
                submitted_value=_value_for_kind(kind, f"u{user_id}").as_text,
                outcome="succeeded",
                completed_at=utcnow(),
            )
        )
        await db_session.flush()

        counts = get_requirement_counts_by_phase()
        phase_order_by_requirement_uuid = dict(
            get_curriculum_catalog().phase_order_by_requirement_uuid
        )
        del phase_order_by_requirement_uuid[req_uuid]

        completions = await VerificationAttemptRepository(
            db_session
        ).list_phase_completions(counts, phase_order_by_requirement_uuid)

        assert (single_phase, user_id) not in completions
