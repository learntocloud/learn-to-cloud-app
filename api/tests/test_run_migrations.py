"""Tests for the migration runner's post-upgrade verification.

The verification step is defense-in-depth against the class of bug that
caused issue #432: a silent-failure path in env.py let migrations report
success while the schema stayed at an older revision. With these checks,
even if a swallow ever creeps back in, the script will still exit non-zero
when ``alembic_version`` doesn't match the script directory head.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts import run_migrations as runner


class _FakeMigrationCtx:
    def __init__(self, heads: list[str]) -> None:
        self._heads = heads

    def get_current_heads(self) -> tuple[str, ...]:
        return tuple(self._heads)


class _FakeScript:
    def __init__(self, heads: list[str]) -> None:
        self._heads = heads

    def get_heads(self) -> list[str]:
        return list(self._heads)


def _patch_runner(
    monkeypatch: pytest.MonkeyPatch,
    *,
    script_heads: list[str],
    db_heads: list[str],
    upgrade_should_raise: Exception | None = None,
) -> MagicMock:
    """Set up the common monkeypatches used by every verification test."""
    upgrade_mock = MagicMock()
    if upgrade_should_raise is not None:
        upgrade_mock.side_effect = upgrade_should_raise

    monkeypatch.setattr(runner.alembic.command, "upgrade", upgrade_mock)
    monkeypatch.setattr(
        runner.ScriptDirectory,
        "from_config",
        lambda _cfg: _FakeScript(script_heads),
    )
    monkeypatch.setattr(
        runner.MigrationContext,
        "configure",
        lambda _conn: _FakeMigrationCtx(db_heads),
    )

    fake_engine = MagicMock()
    fake_engine.connect.return_value.__enter__.return_value = MagicMock()
    fake_engine.connect.return_value.__exit__.return_value = False
    monkeypatch.setattr(runner, "create_engine", lambda _url: fake_engine)
    monkeypatch.setattr(runner, "get_sync_database_url", lambda: "sqlite:///:memory:")
    return upgrade_mock


def test_main_succeeds_when_schema_at_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    upgrade_mock = _patch_runner(monkeypatch, script_heads=["0023"], db_heads=["0023"])

    monkeypatch.chdir(tmp_path)
    (tmp_path / "alembic.ini").write_text("[alembic]\nscript_location = alembic\n")

    runner.main()

    upgrade_mock.assert_called_once()


def test_main_raises_when_db_below_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The exact production failure mode: alembic.command.upgrade returns
    successfully (because env.py used to swallow), but the version row
    didn't actually advance. The script-level check must catch this.
    """
    _patch_runner(monkeypatch, script_heads=["0023"], db_heads=["0019"])

    monkeypatch.chdir(tmp_path)
    (tmp_path / "alembic.ini").write_text("[alembic]\nscript_location = alembic\n")

    with pytest.raises(RuntimeError, match="Migration verification failed"):
        runner.main()


def test_main_raises_when_db_has_no_version_row(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """First-time deploy where upgrade silently no-ops: alembic_version
    row is empty but script directory has heads. Must not be treated as
    success.
    """
    _patch_runner(monkeypatch, script_heads=["0023"], db_heads=[])

    monkeypatch.chdir(tmp_path)
    (tmp_path / "alembic.ini").write_text("[alembic]\nscript_location = alembic\n")

    with pytest.raises(RuntimeError, match="Migration verification failed"):
        runner.main()


def test_main_propagates_upgrade_exception(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When alembic.command.upgrade itself raises, the exception must
    propagate. The verification step should not run after a failed upgrade.
    """
    boom = RuntimeError("alembic exploded")
    _patch_runner(
        monkeypatch,
        script_heads=["0023"],
        db_heads=["0019"],
        upgrade_should_raise=boom,
    )

    monkeypatch.chdir(tmp_path)
    (tmp_path / "alembic.ini").write_text("[alembic]\nscript_location = alembic\n")

    with pytest.raises(RuntimeError, match="alembic exploded"):
        runner.main()


def test_get_sync_database_url_converts_asyncpg_to_psycopg2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The URL helper must produce a psycopg2 URL so alembic can use
    synchronous drivers; asyncpg-only URLs would crash at engine init.
    """
    from learn_to_cloud import _migrations_url

    fake_settings = MagicMock()
    fake_settings.use_azure_postgres = False
    fake_settings.database_url = (
        "postgresql+asyncpg://postgres:postgres@db:5432/test_learn_to_cloud"
    )

    with patch.object(_migrations_url, "get_settings", return_value=fake_settings):
        url = _migrations_url.get_sync_database_url()

    assert url.startswith("postgresql+psycopg2://")
    assert "+asyncpg" not in url
