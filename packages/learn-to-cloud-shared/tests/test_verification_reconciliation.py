"""Integration tests for the read-only reconciliation report."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from learn_to_cloud_shared.models import (
    CurriculumPhase,
    CurriculumRequirement,
    LearnerStepCompletion,
    Submission,
    User,
    VerificationAttempt,
    VerificationJob,
)
from learn_to_cloud_shared.verification_reconciliation import (
    ReconciliationReport,
    format_report,
    run_reconciliation,
)

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
USER_ID = 90001


async def _make_user(db_session: AsyncSession) -> None:
    db_session.add(User(id=USER_ID, github_username="reconuser"))
    await db_session.flush()


async def _make_requirement(db_session: AsyncSession) -> uuid.UUID:
    phase = CurriculumPhase(
        uuid=uuid.uuid4(),
        slug=f"phase-{uuid.uuid4().hex[:8]}",
        name="P",
        description="d",
        short_description="s",
        order=0,
    )
    db_session.add(phase)
    await db_session.flush()
    requirement = CurriculumRequirement(
        uuid=uuid.uuid4(),
        phase_uuid=phase.uuid,
        slug=f"req-{uuid.uuid4().hex[:8]}",
        name="R",
        description="d",
        submission_type="profile_readme",
        submission_value_kind="github_url",
        order=0,
    )
    db_session.add(requirement)
    await db_session.flush()
    return requirement.uuid


async def _make_submission(
    db_session: AsyncSession,
    requirement_uuid: uuid.UUID,
    *,
    is_validated: bool = True,
) -> int:
    submission = Submission(
        user_id=USER_ID,
        requirement_uuid=requirement_uuid,
        submitted_value="https://github.com/octocat/repo",
        submission_value_kind="github_url",
        github_url="https://github.com/octocat/repo",
        is_validated=is_validated,
        validated_at=_NOW if is_validated else None,
        verification_completed=True,
    )
    db_session.add(submission)
    await db_session.flush()
    return submission.id


async def _make_job(
    db_session: AsyncSession,
    requirement_uuid: uuid.UUID,
    *,
    result_submission_id: int | None,
) -> uuid.UUID:
    job = VerificationJob(
        id=uuid.uuid4(),
        user_id=USER_ID,
        requirement_uuid=requirement_uuid,
        submission_value_kind="github_url",
        github_url="https://github.com/octocat/repo",
        submitted_value="https://github.com/octocat/repo",
        result_submission_id=result_submission_id,
    )
    db_session.add(job)
    await db_session.flush()
    return job.id


def _attempt(
    requirement_uuid: uuid.UUID,
    *,
    attempt_id: uuid.UUID | None = None,
    outcome: str | None = "succeeded",
    legacy_job_id: uuid.UUID | None = None,
    legacy_submission_id: int | None = None,
    snapshot_source: str = "reconstructed",
) -> VerificationAttempt:
    # ``submitted`` attempts must carry a real snapshot + hash per the
    # table CHECK; ``reconstructed`` history may leave them NULL.
    submitted = snapshot_source == "submitted"
    return VerificationAttempt(
        id=attempt_id or uuid.uuid4(),
        user_id=USER_ID,
        requirement_uuid=requirement_uuid,
        snapshot_source=snapshot_source,
        requirement_snapshot={"uuid": str(requirement_uuid)} if submitted else None,
        requirement_snapshot_hash="deadbeef" if submitted else None,
        submission_value_kind="github_url",
        submitted_value="https://github.com/octocat/repo",
        outcome=outcome,
        completed_at=_NOW if outcome is not None else None,
        terminal_source="migration" if outcome is not None else None,
        legacy_job_id=legacy_job_id,
        legacy_submission_id=legacy_submission_id,
    )


class TestFullyReconciled:
    async def test_ok_when_new_and_legacy_agree(self, db_session: AsyncSession):
        await _make_user(db_session)
        req = await _make_requirement(db_session)
        submission_id = await _make_submission(db_session, req, is_validated=True)
        job_id = await _make_job(db_session, req, result_submission_id=submission_id)
        db_session.add(
            _attempt(
                req,
                attempt_id=job_id,
                outcome="succeeded",
                legacy_job_id=job_id,
                legacy_submission_id=submission_id,
            )
        )
        await db_session.flush()

        report = await run_reconciliation(db_session)

        assert report.ok, report.divergences
        assert report.row_counts["verification_attempts"] == 1
        assert report.row_counts["verification_jobs"] == 1


class TestDivergences:
    async def test_linked_outcome_mismatch(self, db_session: AsyncSession):
        await _make_user(db_session)
        req = await _make_requirement(db_session)
        submission_id = await _make_submission(db_session, req, is_validated=True)
        job_id = await _make_job(db_session, req, result_submission_id=submission_id)
        # Attempt claims 'failed' but the linked submission is validated.
        db_session.add(
            _attempt(
                req,
                attempt_id=job_id,
                outcome="failed",
                legacy_job_id=job_id,
                legacy_submission_id=submission_id,
            )
        )
        await db_session.flush()

        report = await run_reconciliation(db_session)

        assert len(report.linked_outcome_mismatches) == 1
        mismatch = report.linked_outcome_mismatches[0]
        assert mismatch.actual_outcome == "failed"
        assert mismatch.expected_outcome == "succeeded"

    async def test_active_uniqueness_violation(self, db_session: AsyncSession):
        from sqlalchemy import text

        await _make_user(db_session)
        req = await _make_requirement(db_session)
        # The partial unique index normally makes two active attempts
        # impossible; drop it inside this rolled-back transaction so the
        # reconciliation report's defense-in-depth check can be exercised.
        await db_session.execute(
            text("DROP INDEX uq_verification_attempts_active_user_req")
        )
        db_session.add(_attempt(req, outcome=None, legacy_job_id=uuid.uuid4()))
        db_session.add(_attempt(req, outcome=None, legacy_job_id=uuid.uuid4()))
        await db_session.flush()

        report = await run_reconciliation(db_session)

        assert len(report.active_uniqueness_violations) == 1
        assert report.active_uniqueness_violations[0].active_count == 2

    async def test_legacy_only_job_and_submission(self, db_session: AsyncSession):
        await _make_user(db_session)
        req = await _make_requirement(db_session)
        submission_id = await _make_submission(db_session, req)
        job_id = await _make_job(db_session, req, result_submission_id=submission_id)
        # No attempts created for either legacy row.
        report = await run_reconciliation(db_session)

        assert job_id in report.legacy_only_jobs
        assert submission_id in report.legacy_only_submissions

    async def test_dangling_provenance(self, db_session: AsyncSession):
        await _make_user(db_session)
        req = await _make_requirement(db_session)
        attempt_id = uuid.uuid4()
        db_session.add(
            _attempt(
                req,
                attempt_id=attempt_id,
                legacy_job_id=uuid.uuid4(),  # points at a non-existent job
            )
        )
        await db_session.flush()

        report = await run_reconciliation(db_session)

        assert attempt_id in report.dangling_job_provenance

    async def test_reconstructed_attempt_without_provenance_is_flagged(
        self, db_session: AsyncSession
    ):
        await _make_user(db_session)
        req = await _make_requirement(db_session)
        attempt_id = uuid.uuid4()
        db_session.add(
            _attempt(
                req,
                attempt_id=attempt_id,
                snapshot_source="reconstructed",
                legacy_job_id=None,
                legacy_submission_id=None,
            )
        )
        await db_session.flush()

        report = await run_reconciliation(db_session)

        assert attempt_id in report.attempts_without_provenance

    async def test_submitted_attempt_without_provenance_is_not_flagged(
        self, db_session: AsyncSession
    ):
        # Genuine future submitted attempts have no legacy provenance and
        # must not make the report divergent.
        await _make_user(db_session)
        req = await _make_requirement(db_session)
        attempt_id = uuid.uuid4()
        db_session.add(
            _attempt(
                req,
                attempt_id=attempt_id,
                snapshot_source="submitted",
                legacy_job_id=None,
                legacy_submission_id=None,
            )
        )
        await db_session.flush()

        report = await run_reconciliation(db_session)

        assert attempt_id not in report.attempts_without_provenance
        assert report.ok, report.divergences

    async def test_step_completion_divergence(self, db_session: AsyncSession):
        await _make_user(db_session)
        extra_step = uuid.uuid4()
        # learner_step_completions has no FK, so an "extra" completion with
        # no matching step_progress row is detectable directly.
        db_session.add(
            LearnerStepCompletion(
                user_id=USER_ID, step_uuid=extra_step, completed_at=_NOW
            )
        )
        await db_session.flush()

        report = await run_reconciliation(db_session)

        assert (USER_ID, extra_step) in report.step_completions_extra


class TestFormatReport:
    def test_ok_report_renders_ok(self):
        report = ReconciliationReport(row_counts={"verification_attempts": 3})
        rendered = format_report(report)
        assert "OK -- fully reconciled" in rendered
        assert "verification_attempts" in rendered

    def test_divergent_report_flags_result(self):
        report = ReconciliationReport(
            row_counts={},
            attempts_without_provenance=[uuid.uuid4()],
        )
        assert not report.ok
        assert "DIVERGENT" in format_report(report)
