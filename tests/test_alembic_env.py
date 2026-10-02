"""Unit tests for the migrations ``env.py`` URL helpers.

The end-to-end regression for issue #432 lives in
``test_alembic_env_regression.py``, which runs ``alembic upgrade head``
against a deliberately failing migration and asserts the failure propagates.

``env.py`` runs migrations at import time, so we can't just ``import`` it.
We load it with ``importlib.util`` after monkeypatching the alembic context
to skip ``run()``.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from importlib.resources import files
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from alembic import context as real_context

_ENV_PATH = Path(str(files("learn_to_cloud").joinpath("migrations", "env.py")))


def _load_env_module(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """Load ``env.py`` as a module without executing ``run()``."""

    monkeypatch.setattr(real_context, "is_offline_mode", lambda: True)
    monkeypatch.setattr(real_context, "configure", lambda **_: None)

    fake_config = MagicMock()
    fake_config.cmd_opts = None
    monkeypatch.setattr(real_context, "config", fake_config, raising=False)

    class _NoopTx:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(real_context, "begin_transaction", lambda: _NoopTx())
    monkeypatch.setattr(real_context, "run_migrations", lambda: None)

    spec = importlib.util.spec_from_file_location("_env_under_test", _ENV_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_env_under_test"] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("_env_under_test", None)
    return module


def test_get_sync_database_url_converts_asyncpg_to_psycopg2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = _load_env_module(monkeypatch)

    fake_settings = MagicMock()
    fake_settings.database.use_azure_postgres = False
    fake_settings.database.url = (
        "postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/test_learn_to_cloud"
    )
    monkeypatch.setattr(env, "get_migration_settings", lambda: fake_settings)

    url = env._get_sync_database_url()

    assert url.startswith("postgresql+psycopg2://")
    assert "+asyncpg" not in url
