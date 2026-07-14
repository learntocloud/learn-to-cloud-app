"""Data-driven tests for the verification-attempt / step-completion backfill.

Seeds representative legacy shapes at revision 0048, runs migration 0049,
and asserts the backfill, mirroring trigger, and preflight behaviour.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from learn_to_cloud_shared.verification_provenance import (
    attempt_id_for_orphan_submission,
)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

MIGRATION_DB = "test_verification_backfill_migrations"
_BEFORE = "0048_validate_deployment_architecture_type"
_TABLES = "0049_add_verification_attempts_and_step_completions"
_INDEXES = "0050_verification_attempts_concurrent_indexes"

os.environ.setdefault(
    "POSTGRES_VERIFICATION_FUNCTIONS_ROLE",
    "ltc_verification_functions_dev",
)


def _sync_url() -> str:
    raw = os.environ.get(
        "DATABASE__URL",
        "postgresql+asyncpg://postgres:postgres@db:5432/learntocloud",
    )
    return raw.replace("+asyncpg", "+psycopg2")


def _admin_url() -> str:
    return _sync_url().rsplit("/", 1)[0] + "/postgres"


@pytest.fixture()
def alembic_config():
    from pytest_alembic.config import Config

    return Config(
        config_options={
            "file": str(Path(__file__).parent.parent / "alembic.ini"),
            "script_location": str(Path(__file__).parent.parent / "alembic"),
        },
    )


@pytest.fixture()
def alembic_engine():
    admin_eng = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    with admin_eng.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{MIGRATION_DB}' AND pid <> pg_backend_pid()"
            )
        )
        conn.execute(text(f"DROP DATABASE IF EXISTS {MIGRATION_DB}"))
        conn.execute(text(f"CREATE DATABASE {MIGRATION_DB}"))
    admin_eng.dispose()

    mig_url = _sync_url().rsplit("/", 1)[0] + f"/{MIGRATION_DB}"
    engine = create_engine(mig_url)
    yield engine
    engine.dispose()

    admin_eng = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    with admin_eng.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{MIGRATION_DB}' AND pid <> pg_backend_pid()"
            )
        )
        conn.execute(text(f"DROP DATABASE IF EXISTS {MIGRATION_DB}"))
    admin_eng.dispose()


_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _seed_curriculum(session: Session) -> dict[str, uuid.UUID]:
    """Insert a phase/topic/step plus github + token requirements."""
    from learn_to_cloud_shared.models import (
        CurriculumPhase,
        CurriculumRequirement,
        CurriculumStep,
        CurriculumTopic,
    )

    phase = CurriculumPhase(
        uuid=uuid.uuid4(),
        slug="phase0",
        name="Phase 0",
        description="d",
        short_description="s",
        order=0,
    )
    session.add(phase)
    session.flush()
    topic = CurriculumTopic(
        uuid=uuid.uuid4(),
        phase_uuid=phase.uuid,
        slug="topic0",
        name="Topic 0",
        description="d",
        order=0,
    )
    session.add(topic)
    session.flush()
    step = CurriculumStep(
        uuid=uuid.uuid4(),
        topic_uuid=topic.uuid,
        slug="step0",
        order=0,
    )
    stale_step = CurriculumStep(
        uuid=uuid.uuid4(),
        topic_uuid=topic.uuid,
        slug="step-stale",
        order=1,
        deleted_at=_NOW,
    )
    req_github = CurriculumRequirement(
        uuid=uuid.uuid4(),
        phase_uuid=phase.uuid,
        slug="req-github",
        name="GitHub requirement",
        description="d",
        submission_type="profile_readme",
        submission_value_kind="github_url",
        order=0,
    )
    req_token = CurriculumRequirement(
        uuid=uuid.uuid4(),
        phase_uuid=phase.uuid,
        slug="req-token",
        name="Token requirement",
        description="d",
        submission_type="ctf_token",
        submission_value_kind="token",
        order=1,
    )
    session.add_all([step, stale_step, req_github, req_token])
    session.flush()
    return {
        "step": step.uuid,
        "stale_step": stale_step.uuid,
        "req_github": req_github.uuid,
        "req_token": req_token.uuid,
    }


def _make_submission(
    session: Session,
    *,
    user_id: int,
    requirement_uuid: uuid.UUID,
    is_validated: bool,
    verification_completed: bool,
) -> int:
    from learn_to_cloud_shared.models import Submission

    submission = Submission(
        user_id=user_id,
        requirement_uuid=requirement_uuid,
        submitted_value="https://github.com/octocat/repo",
        submission_value_kind="github_url",
        github_url="https://github.com/octocat/repo",
        is_validated=is_validated,
        validated_at=_NOW if is_validated else None,
        verification_completed=verification_completed,
    )
    session.add(submission)
    session.flush()
    return submission.id


def _make_job(
    session: Session,
    *,
    user_id: int,
    requirement_uuid: uuid.UUID,
    value_kind: str = "github_url",
    result_submission_id: int | None = None,
) -> uuid.UUID:
    from learn_to_cloud_shared.models import VerificationJob

    job_id = uuid.uuid4()
    if value_kind == "github_url":
        typed = {
            "github_url": "https://github.com/octocat/repo",
            "submitted_value": "https://github.com/octocat/repo",
        }
    else:
        typed = {"token_value": "tok-123", "submitted_value": "tok-123"}
    job = VerificationJob(
        id=job_id,
        user_id=user_id,
        requirement_uuid=requirement_uuid,
        submission_value_kind=value_kind,
        result_submission_id=result_submission_id,
        traceparent="00-abc-def-01",
        **typed,
    )
    session.add(job)
    session.flush()
    return job_id


def _seed(engine) -> dict:
    """Seed every representative shape. Returns identifiers for assertions."""
    from learn_to_cloud_shared.models import StepProgress, User

    with Session(engine) as session:
        user = User(id=1001, github_username="octocat")
        session.add(user)
        session.flush()
        cur = _seed_curriculum(session)

        # Step progress: one active step + one stale (soft-deleted) step.
        session.add_all(
            [
                StepProgress(user_id=1001, step_uuid=cur["step"], completed_at=_NOW),
                StepProgress(
                    user_id=1001, step_uuid=cur["stale_step"], completed_at=_NOW
                ),
            ]
        )

        # 1. linked job -> validated submission (succeeded)
        s1 = _make_submission(
            session,
            user_id=1001,
            requirement_uuid=cur["req_github"],
            is_validated=True,
            verification_completed=True,
        )
        j1 = _make_job(
            session,
            user_id=1001,
            requirement_uuid=cur["req_github"],
            result_submission_id=s1,
        )
        # 2. linked job -> completed-not-validated submission (failed)
        s2 = _make_submission(
            session,
            user_id=1001,
            requirement_uuid=cur["req_github"],
            is_validated=False,
            verification_completed=True,
        )
        j2 = _make_job(
            session,
            user_id=1001,
            requirement_uuid=cur["req_github"],
            result_submission_id=s2,
        )
        # 3. linked job -> not-completed submission (server_error)
        s3 = _make_submission(
            session,
            user_id=1001,
            requirement_uuid=cur["req_github"],
            is_validated=False,
            verification_completed=False,
        )
        j3 = _make_job(
            session,
            user_id=1001,
            requirement_uuid=cur["req_github"],
            result_submission_id=s3,
        )
        # 4. two jobs linked to one submission (both succeeded, both kept)
        s4 = _make_submission(
            session,
            user_id=1001,
            requirement_uuid=cur["req_github"],
            is_validated=True,
            verification_completed=True,
        )
        j4a = _make_job(
            session,
            user_id=1001,
            requirement_uuid=cur["req_github"],
            result_submission_id=s4,
        )
        j4b = _make_job(
            session,
            user_id=1001,
            requirement_uuid=cur["req_github"],
            result_submission_id=s4,
        )
        # 5. unlinked job (active) on a different requirement
        j5 = _make_job(
            session,
            user_id=1001,
            requirement_uuid=cur["req_token"],
            value_kind="token",
            result_submission_id=None,
        )
        # 6. orphan submission with no job (succeeded)
        s6 = _make_submission(
            session,
            user_id=1001,
            requirement_uuid=cur["req_github"],
            is_validated=True,
            verification_completed=True,
        )
        session.commit()

    return {
        "cur": cur,
        "j1": j1,
        "j2": j2,
        "j3": j3,
        "j4a": j4a,
        "j4b": j4b,
        "j5": j5,
        "s6": s6,
    }


def _maybe_attempt(engine, attempt_id: uuid.UUID) -> dict | None:
    with engine.connect() as conn:
        row = (
            conn.execute(
                text("SELECT * FROM verification_attempts WHERE id = :id"),
                {"id": attempt_id},
            )
            .mappings()
            .first()
        )
    return dict(row) if row else None


def _fetch_attempt(engine, attempt_id: uuid.UUID) -> dict:
    attempt = _maybe_attempt(engine, attempt_id)
    assert attempt is not None, f"expected attempt {attempt_id} to exist"
    return attempt


@pytest.mark.migration_chain
def test_backfill_all_shapes(alembic_runner, alembic_engine):
    alembic_runner.migrate_up_to(_BEFORE)
    ids = _seed(alembic_engine)
    alembic_runner.migrate_up_one()

    # 1-3: linked outcome mappings.
    assert _fetch_attempt(alembic_engine, ids["j1"])["outcome"] == "succeeded"
    assert _fetch_attempt(alembic_engine, ids["j2"])["outcome"] == "failed"
    assert _fetch_attempt(alembic_engine, ids["j3"])["outcome"] == "server_error"

    a1 = _fetch_attempt(alembic_engine, ids["j1"])
    assert a1["snapshot_source"] == "reconstructed"
    assert a1["legacy_job_id"] == ids["j1"]
    assert a1["completed_at"] is not None
    assert a1["requirement_snapshot"] is not None
    assert a1["terminal_source"] == "migration"
    assert a1["traceparent"] == "00-abc-def-01"

    # 4: both jobs linked to one submission are preserved as succeeded.
    assert _fetch_attempt(alembic_engine, ids["j4a"])["outcome"] == "succeeded"
    assert _fetch_attempt(alembic_engine, ids["j4b"])["outcome"] == "succeeded"

    # 5: unlinked job -> active attempt.
    a5 = _fetch_attempt(alembic_engine, ids["j5"])
    assert a5["outcome"] is None
    assert a5["completed_at"] is None
    assert a5["legacy_submission_id"] is None

    # 6: orphan submission -> deterministic UUIDv5 attempt.
    orphan_id = attempt_id_for_orphan_submission(ids["s6"])
    a6 = _maybe_attempt(alembic_engine, orphan_id)
    assert a6 is not None
    assert a6["outcome"] == "succeeded"
    assert a6["legacy_job_id"] is None
    assert a6["legacy_submission_id"] == ids["s6"]


@pytest.mark.migration_chain
def test_concurrent_indexes_created_by_0050(alembic_runner, alembic_engine):
    alembic_runner.migrate_up_to(_BEFORE)
    _seed(alembic_engine)
    # Runs 0049 (tables + backfill) then 0050 (concurrent index builds).
    alembic_runner.migrate_up_to(_INDEXES)

    with alembic_engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT c.relname AS name, i.indisvalid
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                JOIN pg_class t ON t.oid = i.indrelid
                WHERE t.relname = 'verification_attempts'
                """
            )
        ).all()

    by_name = {r.name: r.indisvalid for r in rows}
    for index_name in (
        "uq_verification_attempts_active_user_req",
        "ix_verification_attempts_succeeded_user_req",
        "ix_verification_attempts_user_req_created",
    ):
        assert index_name in by_name, f"{index_name} missing"
        assert by_name[index_name] is True, f"{index_name} is INVALID"


def _index_is_valid(engine, index_name: str) -> bool | None:
    with engine.connect() as conn:
        return conn.execute(
            text(
                """
                SELECT i.indisvalid
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                WHERE c.relname = :name
                """
            ),
            {"name": index_name},
        ).scalar()


@pytest.mark.migration_chain
def test_0050_recovers_invalid_index_on_retry(alembic_runner, alembic_engine):
    index_name = "uq_verification_attempts_active_user_req"
    alembic_runner.migrate_up_to(_BEFORE)
    ids = _seed(alembic_engine)
    # Run 0049 so verification_attempts exists and is backfilled; 0050 has
    # NOT run yet, so the unique index is absent.
    alembic_runner.migrate_up_to(_TABLES)
    assert _index_is_valid(alembic_engine, index_name) is None

    # Simulate a prior failed 0050 run: force a CREATE UNIQUE INDEX
    # CONCURRENTLY to fail (two active attempts on the same user/req),
    # which leaves the index behind in an INVALID state.
    dup_id = uuid.uuid4()
    with alembic_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO verification_attempts (
                    id, user_id, requirement_uuid, snapshot_source,
                    submission_value_kind, submitted_value, outcome,
                    created_at, updated_at
                ) VALUES (
                    :id, 1001, :req, 'reconstructed', 'token', 'tok-dup',
                    NULL, :t, :t
                )
                """
            ),
            {"id": dup_id, "req": ids["cur"]["req_token"], "t": _NOW},
        )

    autocommit = alembic_engine.execution_options(isolation_level="AUTOCOMMIT")
    with autocommit.connect() as conn:
        with pytest.raises(Exception):
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX CONCURRENTLY "
                    f"{index_name} "
                    "ON verification_attempts (user_id, requirement_uuid) "
                    "WHERE outcome IS NULL"
                )
            )
    # The failed build left an INVALID index that IF NOT EXISTS alone would
    # skip on retry.
    assert _index_is_valid(alembic_engine, index_name) is False

    # Remove the duplicate so the rebuild can succeed, then run 0050.
    with alembic_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM verification_attempts WHERE id = :id"),
            {"id": dup_id},
        )
    alembic_runner.migrate_up_one()

    # 0050 dropped the invalid index and rebuilt it valid.
    assert _index_is_valid(alembic_engine, index_name) is True


@pytest.mark.migration_chain
def test_step_completions_backfill_and_stale_uuid(alembic_runner, alembic_engine):
    alembic_runner.migrate_up_to(_BEFORE)
    ids = _seed(alembic_engine)
    alembic_runner.migrate_up_one()

    with alembic_engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT step_uuid FROM learner_step_completions "
                    "WHERE user_id = 1001 ORDER BY step_uuid"
                )
            )
            .scalars()
            .all()
        )

    # Both the active and the stale (soft-deleted) step completions mirror,
    # because learner_step_completions has no FK to the curriculum.
    assert set(rows) == {ids["cur"]["step"], ids["cur"]["stale_step"]}


@pytest.mark.migration_chain
def test_mirror_trigger_insert_delete_and_idempotent(alembic_runner, alembic_engine):
    alembic_runner.migrate_up_to(_BEFORE)
    _seed(alembic_engine)
    alembic_runner.migrate_up_one()

    new_step = _extra_step(alembic_engine)

    with alembic_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO step_progress (user_id, step_uuid, completed_at) "
                "VALUES (1001, :s, :t)"
            ),
            {"s": new_step, "t": _NOW},
        )
    assert _completion_count(alembic_engine, new_step) == 1

    # Idempotent: a duplicate step_progress insert (same key) must not raise
    # or create a second mirror row.
    with alembic_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO step_progress (user_id, step_uuid, completed_at) "
                "VALUES (1001, :s, :t) "
                "ON CONFLICT (user_id, step_uuid) DO NOTHING"
            ),
            {"s": new_step, "t": _NOW},
        )
    assert _completion_count(alembic_engine, new_step) == 1

    # DELETE mirrors through to the completion table.
    with alembic_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM step_progress WHERE user_id = 1001 AND step_uuid = :s"),
            {"s": new_step},
        )
    assert _completion_count(alembic_engine, new_step) == 0


@pytest.mark.migration_chain
def test_explicit_dual_write_is_safe_alongside_mirror_trigger(
    alembic_runner, alembic_engine
):
    """PR5's explicit dual-write (learner_step_completions insert, then the
    legacy step_progress insert) must coexist with the 0049 mirror trigger:
    the trigger's own INSERT/DELETE against learner_step_completions is
    ``ON CONFLICT DO NOTHING`` / a plain ``DELETE``, so it becomes a no-op
    once the explicit write already landed -- regardless of write order."""
    alembic_runner.migrate_up_to(_BEFORE)
    _seed(alembic_engine)
    alembic_runner.migrate_up_one()

    new_step = _extra_step(alembic_engine)

    # Explicit authoritative write first (what LearnerStepCompletionRepository
    # does), then the legacy write the trigger mirrors from.
    with alembic_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO learner_step_completions "
                "(user_id, step_uuid, completed_at) "
                "VALUES (1001, :s, :t) "
                "ON CONFLICT (user_id, step_uuid) DO NOTHING"
            ),
            {"s": new_step, "t": _NOW},
        )
        conn.execute(
            text(
                "INSERT INTO step_progress (user_id, step_uuid, completed_at) "
                "VALUES (1001, :s, :t)"
            ),
            {"s": new_step, "t": _NOW},
        )
    # No unique-violation from the trigger's own insert, and no duplicate row.
    assert _completion_count(alembic_engine, new_step) == 1

    # Explicit delete first, then the legacy delete the trigger mirrors from.
    with alembic_engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM learner_step_completions "
                "WHERE user_id = 1001 AND step_uuid = :s"
            ),
            {"s": new_step},
        )
        conn.execute(
            text("DELETE FROM step_progress WHERE user_id = 1001 AND step_uuid = :s"),
            {"s": new_step},
        )
    assert _completion_count(alembic_engine, new_step) == 0


@pytest.mark.migration_chain
def test_active_uniqueness_preflight_aborts(alembic_runner, alembic_engine):
    alembic_runner.migrate_up_to(_BEFORE)
    ids = _seed(alembic_engine)

    # Force a second active (unlinked) job for the same (user, requirement)
    # by dropping the guarding unique index first, so the backfill would
    # break the one-active-attempt invariant.
    with alembic_engine.begin() as conn:
        conn.execute(
            text("DROP INDEX IF EXISTS uq_verification_jobs_active_user_req_uuid")
        )
    with Session(alembic_engine) as session:
        _make_job(
            session,
            user_id=1001,
            requirement_uuid=ids["cur"]["req_token"],
            value_kind="token",
            result_submission_id=None,
        )
        session.commit()

    with pytest.raises(Exception, match="one-active-attempt"):
        alembic_runner.migrate_up_one()


def _extra_step(engine) -> uuid.UUID:
    from learn_to_cloud_shared.models import CurriculumStep

    step_uuid = uuid.uuid4()
    with Session(engine) as session:
        topic_uuid = session.execute(
            text("SELECT uuid FROM topics LIMIT 1")
        ).scalar_one()
        session.add(
            CurriculumStep(
                uuid=step_uuid,
                topic_uuid=topic_uuid,
                slug="step-extra",
                order=99,
            )
        )
        session.commit()
    return step_uuid


def _completion_count(engine, step_uuid: uuid.UUID) -> int:
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT count(*) FROM learner_step_completions "
                "WHERE user_id = 1001 AND step_uuid = :s"
            ),
            {"s": step_uuid},
        ).scalar_one()


@pytest.mark.migration_chain
def test_functions_role_grants(alembic_runner, alembic_engine, monkeypatch):
    role = f"ltc_recon_grant_{uuid.uuid4().hex[:10]}"
    monkeypatch.setenv("POSTGRES_VERIFICATION_FUNCTIONS_ROLE", role)

    try:
        # Migrate to the base first with the role absent so earlier
        # grant/revoke migrations no-op; then create the role so only the
        # 0049 grant under test runs against it.
        alembic_runner.migrate_up_to(_BEFORE)

        admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text(f'CREATE ROLE "{role}"'))
        admin.dispose()

        _seed(alembic_engine)
        alembic_runner.migrate_up_one()

        with alembic_engine.connect() as conn:
            granted = set(
                conn.execute(
                    text(
                        """
                        SELECT privilege_type
                        FROM information_schema.role_table_grants
                        WHERE grantee = :role
                          AND table_name = 'verification_attempts'
                        """
                    ),
                    {"role": role},
                ).scalars()
            )
        assert {"SELECT", "INSERT", "UPDATE"} <= granted
        # Least privilege: no DELETE/TRUNCATE at this expand stage.
        assert "DELETE" not in granted
    finally:
        admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    f"WHERE datname = '{MIGRATION_DB}' AND pid <> pg_backend_pid()"
                )
            )
            conn.execute(text(f"DROP DATABASE IF EXISTS {MIGRATION_DB}"))
            conn.execute(text(f'DROP ROLE IF EXISTS "{role}"'))
        admin.dispose()
