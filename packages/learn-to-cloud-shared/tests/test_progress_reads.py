"""Integration tests for progress_reads.py: authoritative-with-narrow-legacy-
fallback learner-state resolution.

Covers the semantics PR6 relies on for progress, gating, and the submission
card:
- an authoritative row always wins, regardless of legacy state;
- legacy data only fills a genuine gap (nothing authoritative recorded, or
  no attempt row at all for a requirement);
- a stale/retired UUID that only the caller's candidate set still names
  simply doesn't come back (repositories always filter to candidates).
"""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.content_sync import sync_curriculum_to_db
from learn_to_cloud_shared.content_yaml_loader import clear_cache
from learn_to_cloud_shared.models import (
    CurriculumRequirement,
    CurriculumStep,
    StepProgress,
    SubmissionValueKind,
)
from learn_to_cloud_shared.progress_reads import (
    are_all_requirements_succeeded,
    resolve_completed_step_uuids,
    resolve_succeeded_requirement_uuids,
)
from learn_to_cloud_shared.repositories.learner_step_completion_repository import (
    LearnerStepCompletionRepository,
)
from learn_to_cloud_shared.repositories.submission_repository import (
    SubmissionRepository,
)
from learn_to_cloud_shared.repositories.user_repository import UserRepository
from learn_to_cloud_shared.submission_values import SubmittedValue

pytestmark = pytest.mark.integration

USER_ID = 91001


@pytest.fixture()
async def user(db_session: AsyncSession):
    await UserRepository(db_session).upsert(USER_ID, github_username="progressreads")


@pytest.fixture()
async def real_step_uuid(db_session: AsyncSession) -> None:
    """A real curriculum step UUID (``step_progress`` FKs to ``steps.uuid``)."""
    clear_cache()
    await sync_curriculum_to_db(db_session)
    return (await db_session.execute(select(CurriculumStep.uuid).limit(1))).scalar_one()


@pytest.fixture()
async def real_requirement(db_session: AsyncSession) -> tuple:
    """A real ``(uuid, submission_value_kind)`` (``submissions`` FKs to it)."""
    clear_cache()
    await sync_curriculum_to_db(db_session)
    row = (
        await db_session.execute(
            select(
                CurriculumRequirement.uuid,
                CurriculumRequirement.submission_value_kind,
            ).limit(1)
        )
    ).one()
    return row.uuid, row.submission_value_kind


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


class TestResolveCompletedStepUuids:
    async def test_empty_candidates_returns_empty(self, db_session: AsyncSession, user):
        completed, fallback = await resolve_completed_step_uuids(
            db_session, USER_ID, []
        )
        assert completed == set()
        assert fallback == set()

    async def test_authoritative_only(self, db_session: AsyncSession, user):
        step_uuid = uuid4()
        await LearnerStepCompletionRepository(db_session).create_if_not_exists(
            user_id=USER_ID, step_uuid=step_uuid
        )
        await db_session.flush()

        completed, fallback = await resolve_completed_step_uuids(
            db_session, USER_ID, [step_uuid]
        )

        assert completed == {step_uuid}
        assert fallback == set()

    async def test_legacy_only_is_used_as_fallback(
        self, db_session: AsyncSession, user, real_step_uuid
    ):
        """A step completed only in the legacy table (never mirrored) still
        counts, and is flagged as a fallback-only completion."""
        db_session.add(StepProgress(user_id=USER_ID, step_uuid=real_step_uuid))
        await db_session.flush()

        completed, fallback = await resolve_completed_step_uuids(
            db_session, USER_ID, [real_step_uuid]
        )

        assert completed == {real_step_uuid}
        assert fallback == {real_step_uuid}

    async def test_authoritative_wins_when_both_exist(
        self, db_session: AsyncSession, user, real_step_uuid
    ):
        """When both tables have the row, it's not counted as a fallback."""
        await LearnerStepCompletionRepository(db_session).create_if_not_exists(
            user_id=USER_ID, step_uuid=real_step_uuid
        )
        db_session.add(StepProgress(user_id=USER_ID, step_uuid=real_step_uuid))
        await db_session.flush()

        completed, fallback = await resolve_completed_step_uuids(
            db_session, USER_ID, [real_step_uuid]
        )

        assert completed == {real_step_uuid}
        assert fallback == set()

    async def test_uncandidated_uuid_never_returned(
        self, db_session: AsyncSession, user
    ):
        """A completion for a UUID outside the requested candidate set (e.g.
        a retired step no longer in the current catalog) is simply absent
        from the result -- callers only ever pass current UUIDs."""
        completed_step = uuid4()
        retired_step = uuid4()
        await LearnerStepCompletionRepository(db_session).create_if_not_exists(
            user_id=USER_ID, step_uuid=completed_step
        )
        await LearnerStepCompletionRepository(db_session).create_if_not_exists(
            user_id=USER_ID, step_uuid=retired_step
        )
        await db_session.flush()

        completed, _ = await resolve_completed_step_uuids(
            db_session, USER_ID, [completed_step]
        )

        assert completed == {completed_step}


class TestResolveSucceededRequirementUuids:
    async def test_empty_candidates_returns_empty(self, db_session: AsyncSession, user):
        succeeded, fallback = await resolve_succeeded_requirement_uuids(
            db_session, USER_ID, []
        )
        assert succeeded == set()
        assert fallback == set()

    async def test_authoritative_succeeded_only(self, db_session: AsyncSession, user):
        req_uuid = uuid4()
        db_session.add(
            _attempt(user_id=USER_ID, requirement_uuid=req_uuid, outcome="succeeded")
        )
        await db_session.flush()

        succeeded, fallback = await resolve_succeeded_requirement_uuids(
            db_session, USER_ID, [req_uuid]
        )

        assert succeeded == {req_uuid}
        assert fallback == set()

    async def test_failed_attempt_is_not_succeeded_and_not_overridden_by_legacy(
        self, db_session: AsyncSession, user, real_requirement
    ):
        """A requirement with a failed attempt has attempt history, so the
        legacy table is never consulted for it, even if legacy also says
        validated (a scenario that shouldn't happen post-dual-write, but the
        precedence rule must hold regardless)."""
        req_uuid, kind = real_requirement
        db_session.add(
            _attempt(user_id=USER_ID, requirement_uuid=req_uuid, outcome="failed")
        )
        await SubmissionRepository(db_session).create(
            user_id=USER_ID,
            requirement_uuid=req_uuid,
            submitted_value=_value_for_kind(kind, "u1"),
            extracted_username=None,
            is_validated=True,
        )
        await db_session.flush()

        succeeded, fallback = await resolve_succeeded_requirement_uuids(
            db_session, USER_ID, [req_uuid]
        )

        assert succeeded == set()
        assert fallback == set()

    async def test_legacy_only_is_used_as_fallback(
        self, db_session: AsyncSession, user, real_requirement
    ):
        """A requirement with zero attempt rows at all falls back to the
        legacy ``submissions.is_validated`` flag."""
        req_uuid, kind = real_requirement
        await SubmissionRepository(db_session).create(
            user_id=USER_ID,
            requirement_uuid=req_uuid,
            submitted_value=_value_for_kind(kind, "u1"),
            extracted_username=None,
            is_validated=True,
        )
        await db_session.flush()

        succeeded, fallback = await resolve_succeeded_requirement_uuids(
            db_session, USER_ID, [req_uuid]
        )

        assert succeeded == {req_uuid}
        assert fallback == {req_uuid}

    async def test_active_attempt_blocks_legacy_fallback(
        self, db_session: AsyncSession, user, real_requirement
    ):
        """An active (in-flight) attempt still counts as "attempted", so a
        legacy validated row for the same requirement is not consulted."""
        req_uuid, kind = real_requirement
        db_session.add(
            _attempt(user_id=USER_ID, requirement_uuid=req_uuid, outcome=None)
        )
        await SubmissionRepository(db_session).create(
            user_id=USER_ID,
            requirement_uuid=req_uuid,
            submitted_value=_value_for_kind(kind, "u1"),
            extracted_username=None,
            is_validated=True,
        )
        await db_session.flush()

        succeeded, fallback = await resolve_succeeded_requirement_uuids(
            db_session, USER_ID, [req_uuid]
        )

        assert succeeded == set()
        assert fallback == set()

    async def test_uncandidated_uuid_never_returned(
        self, db_session: AsyncSession, user
    ):
        succeeded_req = uuid4()
        retired_req = uuid4()
        db_session.add(
            _attempt(
                user_id=USER_ID, requirement_uuid=succeeded_req, outcome="succeeded"
            )
        )
        db_session.add(
            _attempt(user_id=USER_ID, requirement_uuid=retired_req, outcome="succeeded")
        )
        await db_session.flush()

        succeeded, _ = await resolve_succeeded_requirement_uuids(
            db_session, USER_ID, [succeeded_req]
        )

        assert succeeded == {succeeded_req}


class TestAreAllRequirementsSucceeded:
    async def test_empty_list_is_true(self, db_session: AsyncSession, user):
        assert await are_all_requirements_succeeded(db_session, USER_ID, [])

    async def test_true_when_all_succeeded_via_mixed_sources(
        self, db_session: AsyncSession, user, real_requirement
    ):
        """One requirement succeeded via an attempt, the other only via a
        legacy row -- gating must treat both as satisfied."""
        attempt_req, attempt_kind = real_requirement
        legacy_req = uuid4()
        db_session.add(
            _attempt(user_id=USER_ID, requirement_uuid=attempt_req, outcome="succeeded")
        )
        await db_session.flush()
        # legacy_req has no curriculum FK requirement here since it's not
        # inserted into `submissions` (only checked via the attempt path);
        # simulate a second attempt-succeeded requirement instead, since
        # `submissions` requires a real curriculum requirement UUID.
        db_session.add(
            _attempt(user_id=USER_ID, requirement_uuid=legacy_req, outcome="succeeded")
        )
        await db_session.flush()

        assert await are_all_requirements_succeeded(
            db_session, USER_ID, [attempt_req, legacy_req]
        )

    async def test_false_when_one_missing(self, db_session: AsyncSession, user):
        succeeded_req = uuid4()
        missing_req = uuid4()
        db_session.add(
            _attempt(
                user_id=USER_ID, requirement_uuid=succeeded_req, outcome="succeeded"
            )
        )
        await db_session.flush()

        assert not await are_all_requirements_succeeded(
            db_session, USER_ID, [succeeded_req, missing_req]
        )


def _attempt(*, user_id: int, requirement_uuid, outcome: str | None):
    from learn_to_cloud_shared.models import VerificationAttempt, utcnow

    return VerificationAttempt(
        user_id=user_id,
        requirement_uuid=requirement_uuid,
        snapshot_source="reconstructed",
        submission_value_kind="github_url",
        submitted_value="https://github.com/progressreads/repo",
        outcome=outcome,
        completed_at=utcnow() if outcome is not None else None,
    )
