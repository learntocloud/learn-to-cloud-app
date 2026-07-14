"""Read-only reconciliation report for the verification-attempt backfill.

Run after the expand backfill and after later deployments to confirm the
new ``verification_attempts`` / ``learner_step_completions`` tables agree
with the legacy ``verification_jobs`` / ``submissions`` / ``step_progress``
tables. The report never mutates data -- it only runs SELECTs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Shared with the backfill migration so the expected-outcome mapping stays
# identical on both sides of the comparison.
_EXPECTED_OUTCOME_SQL = (
    "CASE WHEN {alias}.is_validated THEN 'succeeded' "
    "WHEN {alias}.verification_completed THEN 'failed' "
    "ELSE 'server_error' END"
)


@dataclass(frozen=True)
class OutcomeMismatch:
    attempt_id: UUID
    user_id: int
    requirement_uuid: UUID
    actual_outcome: str | None
    expected_outcome: str


@dataclass(frozen=True)
class ActiveUniquenessViolation:
    user_id: int
    requirement_uuid: UUID
    active_count: int


@dataclass(frozen=True)
class ReconciliationReport:
    """Structured result of a reconciliation pass. Read-only."""

    row_counts: dict[str, int] = field(default_factory=dict)
    linked_outcome_mismatches: list[OutcomeMismatch] = field(default_factory=list)
    orphan_outcome_mismatches: list[OutcomeMismatch] = field(default_factory=list)
    active_uniqueness_violations: list[ActiveUniquenessViolation] = field(
        default_factory=list
    )
    legacy_only_jobs: list[UUID] = field(default_factory=list)
    legacy_only_submissions: list[int] = field(default_factory=list)
    dangling_job_provenance: list[UUID] = field(default_factory=list)
    dangling_submission_provenance: list[UUID] = field(default_factory=list)
    attempts_without_provenance: list[UUID] = field(default_factory=list)
    step_completions_missing: list[tuple[int, UUID]] = field(default_factory=list)
    step_completions_extra: list[tuple[int, UUID]] = field(default_factory=list)

    @property
    def divergences(self) -> dict[str, int]:
        """Named divergence categories mapped to their row counts."""
        return {
            "linked_outcome_mismatches": len(self.linked_outcome_mismatches),
            "orphan_outcome_mismatches": len(self.orphan_outcome_mismatches),
            "active_uniqueness_violations": len(self.active_uniqueness_violations),
            "legacy_only_jobs": len(self.legacy_only_jobs),
            "legacy_only_submissions": len(self.legacy_only_submissions),
            "dangling_job_provenance": len(self.dangling_job_provenance),
            "dangling_submission_provenance": len(self.dangling_submission_provenance),
            "attempts_without_provenance": len(self.attempts_without_provenance),
            "step_completions_missing": len(self.step_completions_missing),
            "step_completions_extra": len(self.step_completions_extra),
        }

    @property
    def ok(self) -> bool:
        """True when every divergence category is empty."""
        return not any(self.divergences.values())


async def _scalar_count(session: AsyncSession, table: str) -> int:
    result = await session.execute(text(f"SELECT count(*) FROM {table}"))
    return int(result.scalar_one())


async def run_reconciliation(session: AsyncSession) -> ReconciliationReport:
    """Compute a reconciliation report. Runs SELECTs only, never mutates."""
    row_counts = {
        "step_progress": await _scalar_count(session, "step_progress"),
        "learner_step_completions": await _scalar_count(
            session, "learner_step_completions"
        ),
        "submissions": await _scalar_count(session, "submissions"),
        "verification_jobs": await _scalar_count(session, "verification_jobs"),
        "verification_attempts": await _scalar_count(session, "verification_attempts"),
    }

    linked_outcome_mismatches = [
        OutcomeMismatch(
            attempt_id=r.id,
            user_id=r.user_id,
            requirement_uuid=r.requirement_uuid,
            actual_outcome=r.outcome,
            expected_outcome=r.expected_outcome,
        )
        for r in (
            await session.execute(
                text(
                    f"""
                    SELECT a.id, a.user_id, a.requirement_uuid, a.outcome,
                           {_EXPECTED_OUTCOME_SQL.format(alias="s")}
                               AS expected_outcome
                    FROM verification_attempts a
                    JOIN verification_jobs vj ON vj.id = a.legacy_job_id
                    JOIN submissions s ON s.id = vj.result_submission_id
                    WHERE a.outcome IS DISTINCT FROM
                        {_EXPECTED_OUTCOME_SQL.format(alias="s")}
                    ORDER BY a.id
                    """
                )
            )
        ).all()
    ]

    orphan_outcome_mismatches = [
        OutcomeMismatch(
            attempt_id=r.id,
            user_id=r.user_id,
            requirement_uuid=r.requirement_uuid,
            actual_outcome=r.outcome,
            expected_outcome=r.expected_outcome,
        )
        for r in (
            await session.execute(
                text(
                    f"""
                    SELECT a.id, a.user_id, a.requirement_uuid, a.outcome,
                           {_EXPECTED_OUTCOME_SQL.format(alias="s")}
                               AS expected_outcome
                    FROM verification_attempts a
                    JOIN submissions s ON s.id = a.legacy_submission_id
                    WHERE a.legacy_job_id IS NULL
                      AND a.outcome IS DISTINCT FROM
                          {_EXPECTED_OUTCOME_SQL.format(alias="s")}
                    ORDER BY a.id
                    """
                )
            )
        ).all()
    ]

    active_uniqueness_violations = [
        ActiveUniquenessViolation(
            user_id=r.user_id,
            requirement_uuid=r.requirement_uuid,
            active_count=r.active_count,
        )
        for r in (
            await session.execute(
                text(
                    """
                    SELECT user_id, requirement_uuid, count(*) AS active_count
                    FROM verification_attempts
                    WHERE outcome IS NULL
                    GROUP BY user_id, requirement_uuid
                    HAVING count(*) > 1
                    ORDER BY user_id, requirement_uuid
                    """
                )
            )
        ).all()
    ]

    legacy_only_jobs = [
        r.id
        for r in (
            await session.execute(
                text(
                    """
                    SELECT vj.id
                    FROM verification_jobs vj
                    WHERE NOT EXISTS (
                        SELECT 1 FROM verification_attempts a
                        WHERE a.legacy_job_id = vj.id
                    )
                    ORDER BY vj.id
                    """
                )
            )
        ).all()
    ]

    legacy_only_submissions = [
        r.id
        for r in (
            await session.execute(
                text(
                    """
                    SELECT s.id
                    FROM submissions s
                    WHERE NOT EXISTS (
                        SELECT 1 FROM verification_attempts a
                        WHERE a.legacy_submission_id = s.id
                    )
                    ORDER BY s.id
                    """
                )
            )
        ).all()
    ]

    dangling_job_provenance = [
        r.id
        for r in (
            await session.execute(
                text(
                    """
                    SELECT a.id
                    FROM verification_attempts a
                    WHERE a.legacy_job_id IS NOT NULL
                      AND NOT EXISTS (
                        SELECT 1 FROM verification_jobs vj
                        WHERE vj.id = a.legacy_job_id
                    )
                    ORDER BY a.id
                    """
                )
            )
        ).all()
    ]

    dangling_submission_provenance = [
        r.id
        for r in (
            await session.execute(
                text(
                    """
                    SELECT a.id
                    FROM verification_attempts a
                    WHERE a.legacy_submission_id IS NOT NULL
                      AND NOT EXISTS (
                        SELECT 1 FROM submissions s
                        WHERE s.id = a.legacy_submission_id
                    )
                    ORDER BY a.id
                    """
                )
            )
        ).all()
    ]

    # Only reconstructed/backfilled attempts are expected to carry legacy
    # provenance. Genuine future ``submitted`` attempts legitimately have no
    # legacy_job_id/legacy_submission_id, so they must not be flagged.
    attempts_without_provenance = [
        r.id
        for r in (
            await session.execute(
                text(
                    """
                    SELECT id
                    FROM verification_attempts
                    WHERE legacy_job_id IS NULL
                      AND legacy_submission_id IS NULL
                      AND snapshot_source = 'reconstructed'
                    ORDER BY id
                    """
                )
            )
        ).all()
    ]

    step_completions_missing = [
        (r.user_id, r.step_uuid)
        for r in (
            await session.execute(
                text(
                    """
                    SELECT sp.user_id, sp.step_uuid
                    FROM step_progress sp
                    WHERE NOT EXISTS (
                        SELECT 1 FROM learner_step_completions lsc
                        WHERE lsc.user_id = sp.user_id
                          AND lsc.step_uuid = sp.step_uuid
                    )
                    ORDER BY sp.user_id, sp.step_uuid
                    """
                )
            )
        ).all()
    ]

    step_completions_extra = [
        (r.user_id, r.step_uuid)
        for r in (
            await session.execute(
                text(
                    """
                    SELECT lsc.user_id, lsc.step_uuid
                    FROM learner_step_completions lsc
                    WHERE NOT EXISTS (
                        SELECT 1 FROM step_progress sp
                        WHERE sp.user_id = lsc.user_id
                          AND sp.step_uuid = lsc.step_uuid
                    )
                    ORDER BY lsc.user_id, lsc.step_uuid
                    """
                )
            )
        ).all()
    ]

    return ReconciliationReport(
        row_counts=row_counts,
        linked_outcome_mismatches=linked_outcome_mismatches,
        orphan_outcome_mismatches=orphan_outcome_mismatches,
        active_uniqueness_violations=active_uniqueness_violations,
        legacy_only_jobs=legacy_only_jobs,
        legacy_only_submissions=legacy_only_submissions,
        dangling_job_provenance=dangling_job_provenance,
        dangling_submission_provenance=dangling_submission_provenance,
        attempts_without_provenance=attempts_without_provenance,
        step_completions_missing=step_completions_missing,
        step_completions_extra=step_completions_extra,
    )


def format_report(report: ReconciliationReport) -> str:
    """Render a human-readable summary of a reconciliation report."""
    lines = ["Verification backfill reconciliation report", ""]
    lines.append("Row counts:")
    for table, count in report.row_counts.items():
        lines.append(f"  {table:<28} {count}")
    lines.append("")
    lines.append("Divergences:")
    for name, count in report.divergences.items():
        marker = "ok" if count == 0 else "!!"
        lines.append(f"  [{marker}] {name:<32} {count}")
    lines.append("")
    lines.append("RESULT: " + ("OK -- fully reconciled" if report.ok else "DIVERGENT"))
    return "\n".join(lines)
