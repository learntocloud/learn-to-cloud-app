"""Integration tests for stats aggregates (phase completion + counts)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.content_service import get_requirement_counts_by_phase
from learn_to_cloud_shared.content_sync import sync_curriculum_to_db
from learn_to_cloud_shared.content_yaml_loader import clear_cache
from learn_to_cloud_shared.models import (
    CurriculumPhase,
    CurriculumRequirement,
    SubmissionValueKind,
)
from learn_to_cloud_shared.repositories.submission_repository import (
    SubmissionRepository,
)
from learn_to_cloud_shared.repositories.user_repository import UserRepository
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

        counts = await get_requirement_counts_by_phase(db_session)
        completions = await SubmissionRepository(db_session).list_phase_completions(
            counts
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

        counts = await get_requirement_counts_by_phase(db_session)
        completions = await SubmissionRepository(db_session).list_phase_completions(
            counts
        )

        assert (multi_phase, user_id) not in completions

    async def test_empty_counts_returns_empty(self, db_session: AsyncSession):
        repo = SubmissionRepository(db_session)
        assert await repo.list_phase_completions({}) == []

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

        counts = await get_requirement_counts_by_phase(db_session)
        completions = await SubmissionRepository(db_session).list_phase_completions(
            counts
        )

        assert (multi_phase, user_id) in completions
