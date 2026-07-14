"""Integration tests for stats_service.get_stats_page_data."""

from unittest.mock import AsyncMock, patch

import pytest
from learn_to_cloud_shared.content_service import get_requirement_counts_by_phase
from learn_to_cloud_shared.content_sync import sync_curriculum_to_db
from learn_to_cloud_shared.content_yaml_loader import clear_cache
from learn_to_cloud_shared.models import (
    CurriculumPhase,
    CurriculumRequirement,
    SubmissionValueKind,
    User,
    VerificationAttempt,
    utcnow,
)
from learn_to_cloud_shared.repositories.submission_repository import (
    SubmissionRepository,
)
from learn_to_cloud_shared.submission_values import SubmittedValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud.services.stats_service import get_stats_page_data

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _value_for_kind(kind: str, seed: str) -> SubmittedValue:
    value_kind = SubmissionValueKind(kind)
    kwargs = {
        SubmissionValueKind.GITHUB_URL: {"github_url": f"https://github.com/{seed}"},
        SubmissionValueKind.TOKEN: {"token_value": f"token-{seed}"},
        SubmissionValueKind.DEPLOYED_URL: {
            "deployed_url": f"https://{seed}.example.com"
        },
        SubmissionValueKind.TEXT: {"text_value": f"reflection {seed}"},
    }[value_kind]
    return SubmittedValue(kind=value_kind, **kwargs)


async def _reqs_by_phase(db: AsyncSession) -> dict[int, list[tuple]]:
    result = await db.execute(
        select(
            CurriculumPhase.order,
            CurriculumRequirement.uuid,
            CurriculumRequirement.submission_value_kind,
        )
        .join(CurriculumPhase, CurriculumRequirement.phase_uuid == CurriculumPhase.uuid)
        .where(
            CurriculumRequirement.deleted_at.is_(None),
            CurriculumPhase.deleted_at.is_(None),
        )
    )
    by_phase: dict[int, list[tuple]] = {}
    for order, uuid, kind in result.all():
        by_phase.setdefault(order, []).append((uuid, kind))
    return by_phase


async def _validate(db: AsyncSession, user_id: int, reqs: list[tuple]) -> None:
    """Legacy-only completion path: a ``submissions`` row, no attempt row."""
    repo = SubmissionRepository(db)
    for uuid, kind in reqs:
        await repo.create(
            user_id=user_id,
            requirement_uuid=uuid,
            submitted_value=_value_for_kind(kind, f"u{user_id}"),
            extracted_username=None,
            is_validated=True,
        )


async def _succeed_via_attempts(
    db: AsyncSession, user_id: int, reqs: list[tuple]
) -> None:
    """Authoritative completion path: a succeeded ``verification_attempts`` row."""
    for uuid, kind in reqs:
        db.add(
            VerificationAttempt(
                user_id=user_id,
                requirement_uuid=uuid,
                snapshot_source="reconstructed",
                submission_value_kind=kind,
                submitted_value=_value_for_kind(kind, f"u{user_id}").as_text,
                outcome="succeeded",
                completed_at=utcnow(),
            )
        )
    await db.flush()


class TestGetStatsPageData:
    async def test_graduates_are_only_full_curriculum_completers(
        self, db_session: AsyncSession
    ):
        clear_cache()
        await sync_curriculum_to_db(db_session)
        reqs_by_phase = await _reqs_by_phase(db_session)
        counts = get_requirement_counts_by_phase()
        completable = sorted(o for o, c in counts.items() if c > 0)

        # graduate: validates every requirement in every completable phase.
        db_session.add(User(id=60001, github_username="grad"))
        # partial: validates only the first completable phase.
        db_session.add(User(id=60002, github_username="partial"))
        await db_session.flush()

        for order in completable:
            await _validate(db_session, 60001, reqs_by_phase[order])
        await _validate(db_session, 60002, reqs_by_phase[completable[0]])
        await db_session.flush()

        with patch(
            "learn_to_cloud.services.stats_service.get_latest_curriculum_commits",
            new=AsyncMock(return_value=[]),
        ):
            stats = await get_stats_page_data(db_session)

        usernames = {m.github_username for m in stats.graduates}
        assert "grad" in usernames
        assert "partial" not in usernames

        # Funnel starts with the total-accounts level, then covers exactly
        # the completable phases; the first phase counts both users.
        assert stats.funnel[0].is_total is True
        assert stats.funnel[0].label == "Total accounts"
        assert stats.funnel[0].pct_of_total == 100.0
        phase_levels = stats.funnel[1:]
        assert len(phase_levels) == len(completable)
        assert all(
            f"Phase {order}" in lvl.label
            for order, lvl in zip(completable, phase_levels, strict=True)
        )
        first_phase_level = phase_levels[0]
        assert first_phase_level.count >= 2
        assert first_phase_level.pct_of_previous is not None
        assert stats.total_accounts >= 2

    async def test_no_graduates_when_no_full_completions(
        self, db_session: AsyncSession
    ):
        clear_cache()
        await sync_curriculum_to_db(db_session)

        db_session.add(User(id=60003, github_username="nobody"))
        await db_session.flush()

        with patch(
            "learn_to_cloud.services.stats_service.get_latest_curriculum_commits",
            new=AsyncMock(return_value=[]),
        ):
            stats = await get_stats_page_data(db_session)

        assert stats.graduates == []

    async def test_authoritative_verification_attempts_count_as_completions(
        self, db_session: AsyncSession
    ):
        """A succeeded ``verification_attempts`` row (no legacy submission at
        all) is enough to count -- ``verification_attempts`` is now the
        primary source, not merely a fallback."""
        clear_cache()
        await sync_curriculum_to_db(db_session)
        reqs_by_phase = await _reqs_by_phase(db_session)
        counts = get_requirement_counts_by_phase()
        completable = sorted(o for o, c in counts.items() if c > 0)

        db_session.add(User(id=60004, github_username="attemptgrad"))
        await db_session.flush()

        for order in completable:
            await _succeed_via_attempts(db_session, 60004, reqs_by_phase[order])

        with patch(
            "learn_to_cloud.services.stats_service.get_latest_curriculum_commits",
            new=AsyncMock(return_value=[]),
        ):
            stats = await get_stats_page_data(db_session)

        usernames = {m.github_username for m in stats.graduates}
        assert "attemptgrad" in usernames

    async def test_mixed_authoritative_and_legacy_completion_within_one_phase(
        self, db_session: AsyncSession
    ):
        """A phase can be completed via a mix of attempts and legacy rows.

        One requirement succeeds via ``verification_attempts`` (authoritative)
        and another via a legacy ``submissions`` row for the same user/phase
        -- both count toward that phase's completion threshold.
        """
        clear_cache()
        await sync_curriculum_to_db(db_session)
        reqs_by_phase = await _reqs_by_phase(db_session)
        multi_phase = next(
            order for order, reqs in reqs_by_phase.items() if len(reqs) > 1
        )

        db_session.add(User(id=60005, github_username="mixedcompleter"))
        await db_session.flush()

        reqs = reqs_by_phase[multi_phase]
        await _succeed_via_attempts(db_session, 60005, reqs[:1])
        await _validate(db_session, 60005, reqs[1:])
        await db_session.flush()

        counts = get_requirement_counts_by_phase()
        completable = sorted(o for o, c in counts.items() if c > 0)
        assert multi_phase in completable

        with patch(
            "learn_to_cloud.services.stats_service.get_latest_curriculum_commits",
            new=AsyncMock(return_value=[]),
        ):
            stats = await get_stats_page_data(db_session)

        phase_level = next(
            lvl for lvl in stats.funnel if f"Phase {multi_phase}:" in lvl.label
        )
        assert phase_level.count >= 1
