"""Regression test for issue #432: silent migration failure.

Before this fix, ``api/alembic/env.py`` swallowed any exception whose message
contained the substrings ``"duplicate"`` or ``"already exists"``, treating it
as "another worker already applied" and exiting cleanly. A real
``UniqueViolation`` on ``CREATE UNIQUE INDEX`` matched and got silently
ignored, leaving production stuck on an older schema for days while CI
reported successful deploys.

This test invokes the real production env.py against SQLite with a
two-revision chain whose second revision raises a Postgres-style error
containing the words ``"is duplicated"``. The migration must propagate.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_PRODUCTION_ENV_PY = Path(__file__).parent.parent / "alembic" / "env.py"


def _write_fixture_project(root: Path, db_path: Path) -> None:
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

    (root / "alembic.ini").write_text(
        textwrap.dedent(
            f"""\
            [alembic]
            script_location = alembic
            sqlalchemy.url = sqlite:///{db_path}

            [loggers]
            keys = root,alembic
            [handlers]
            keys = console
            [formatters]
            keys = generic
            [logger_root]
            level = WARN
            handlers = console
            qualname =
            [logger_alembic]
            level = INFO
            handlers =
            qualname = alembic
            [handler_console]
            class = StreamHandler
            args = (sys.stderr,)
            level = NOTSET
            formatter = generic
            [formatter_generic]
            format = %(levelname)-5.5s [%(name)s] %(message)s
            """
        )
    )

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
                    "SELECT RAISE(ABORT, "
                    "'Key (user_id, requirement_id) is duplicated.')"
                )

            def downgrade() -> None:
                pass
            '''
        )
    )


def _run_alembic_upgrade(project: Path) -> subprocess.CompletedProcess[str]:
    """Run ``alembic upgrade head`` against the fixture project."""
    env_overrides = {
        "DATABASE_URL": f"sqlite:///{project / 'test.db'}",
        "GITHUB_TOKEN": "test_github_token",
        "LABS_VERIFICATION_SECRET": "test_ctf_secret_must_be_32_chars!",
        "DEBUG": "true",
        "USE_AZURE_POSTGRES": "false",
    }
    import os

    env = {**os.environ, **env_overrides}
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
def test_env_py_does_not_swallow_duplicate_errors(tmp_path: Path) -> None:
    """If env.py ever silently swallows a 'duplicate'-flavored error again,
    this test will fail — alembic upgrade will exit 0 with the SQLite DB
    sitting at 0001_baseline.
    """
    db_path = tmp_path / "test.db"
    _write_fixture_project(tmp_path, db_path)

    result = _run_alembic_upgrade(tmp_path)

    assert result.returncode != 0, (
        "alembic upgrade must propagate the failure. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert "duplicated" in combined.lower() or "Key (user_id" in combined, (
        "The underlying error message must be visible in logs. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
