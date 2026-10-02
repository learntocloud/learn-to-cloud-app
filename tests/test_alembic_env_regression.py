"""Regression test for issue #432: silent migration failure.

Before this fix, the migrations ``env.py`` swallowed any exception whose message
contained the substrings ``"duplicate"`` or ``"already exists"``, treating it
as "another worker already applied" and exiting cleanly. A real
``UniqueViolation`` on ``CREATE UNIQUE INDEX`` matched and got silently
ignored, leaving production stuck on an older schema for days while CI
reported successful deploys.

This test invokes the real production env.py against a dedicated
PostgreSQL database with a
two-revision chain whose second revision raises a Postgres-style error
containing the words ``"is duplicated"``. The migration must propagate.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from importlib.resources import files
from pathlib import Path

import asyncpg
import pytest
from sqlalchemy import make_url

_PRODUCTION_ENV_PY = Path(str(files("learn_to_cloud").joinpath("migrations", "env.py")))
_REGRESSION_DB = "test_alembic_env_regression"


def _base_url():
    return make_url(
        os.environ.get(
            "DATABASE__URL",
            "postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/learntocloud",
        )
    )


async def _recreate_regression_db(*, create: bool) -> None:
    url = _base_url()
    conn = await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database="postgres",
    )
    try:
        await conn.execute(f"DROP DATABASE IF EXISTS {_REGRESSION_DB} WITH (FORCE)")
        if create:
            await conn.execute(f"CREATE DATABASE {_REGRESSION_DB}")
    finally:
        await conn.close()


@pytest.fixture()
def regression_db_url() -> Iterator[str]:
    asyncio.run(_recreate_regression_db(create=True))
    yield _base_url().set(database=_REGRESSION_DB).render_as_string(hide_password=False)
    asyncio.run(_recreate_regression_db(create=False))


def _write_fixture_project(root: Path) -> None:
    """Stand up a minimal alembic project that imports the production env.py."""
    alembic_dir = root / "alembic"
    versions_dir = alembic_dir / "versions"
    versions_dir.mkdir(parents=True)

    shutil.copy(_PRODUCTION_ENV_PY, alembic_dir / "env.py")
    (alembic_dir / "script.py.mako").write_text(
        textwrap.dedent(
            '''\
            """${message}"""
            revision = ${repr(up_revision)}
            down_revision = ${repr(down_revision)}
            branch_labels = ${repr(branch_labels)}
            depends_on = ${repr(depends_on)}

            def upgrade() -> None:
                pass

            def downgrade() -> None:
                pass
            '''
        )
    )

    (root / "alembic.ini").write_text("[alembic]\nscript_location = alembic\n")

    (versions_dir / "0001_baseline.py").write_text(
        textwrap.dedent(
            '''\
            """baseline"""
            from alembic import op
            import sqlalchemy as sa

            revision = "0001_baseline"
            down_revision = None
            branch_labels = None
            depends_on = None

            def upgrade() -> None:
                op.create_table(
                    "things",
                    sa.Column("id", sa.Integer, primary_key=True),
                )

            def downgrade() -> None:
                op.drop_table("things")
            '''
        )
    )

    # This revision raises an error whose message contains the substring
    # "duplicate" — exactly the shape that used to trigger the silent
    # swallow in env.py. The regression test asserts the upgrade fails
    # loudly instead of being treated as benign.
    (versions_dir / "0002_fail.py").write_text(
        textwrap.dedent(
            '''\
            """fails with a duplicate-key style message"""
            from alembic import op

            revision = "0002_fail"
            down_revision = "0001_baseline"
            branch_labels = None
            depends_on = None

            def upgrade() -> None:
                op.execute(
                    "DO $$ BEGIN RAISE EXCEPTION "
                    "'Key (user_id, requirement_id) is duplicated.'; END $$"
                )

            def downgrade() -> None:
                pass
            '''
        )
    )


def _run_alembic_upgrade(
    project: Path, database_url: str
) -> subprocess.CompletedProcess[str]:
    """Run ``alembic upgrade head`` against the fixture project."""
    env = {**os.environ, "DATABASE__URL": database_url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(
    shutil.which(sys.executable) is None,
    reason="Python interpreter not available for subprocess",
)
def test_env_py_does_not_swallow_duplicate_errors(
    tmp_path: Path, regression_db_url: str
) -> None:
    """If env.py ever silently swallows a 'duplicate'-flavored error again,
    this test will fail — alembic upgrade will exit 0 with the database
    sitting at 0001_baseline.
    """
    _write_fixture_project(tmp_path)

    result = _run_alembic_upgrade(tmp_path, regression_db_url)

    assert result.returncode != 0, (
        "alembic upgrade must propagate the failure. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "duplicated" in combined.lower() or "Key (user_id" in combined, (
        "The underlying error message must be visible in logs. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
