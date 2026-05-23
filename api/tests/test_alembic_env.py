"""Unit tests for ``alembic/env.py`` URL helpers.

Head-verification used to live in env.py (``_verify_schema_at_head``) but
was replaced with the official ``alembic.command.current(check_heads=True)``
call from ``scripts/run_migrations.py``. The four tests for the deleted
helper were removed with the function. The end-to-end regression for
issue #432 still lives in ``test_alembic_env_regression.py`` which runs
``alembic upgrade head`` against a deliberately failing migration and
asserts the failure propagates.

``alembic/env.py`` runs migrations at import time, so we can't just
``import``  it. We load it with ``importlib.util`` from the alembic
directory after monkeypatching the alembic context to skip ``run()``.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_ENV_PATH = Path(__file__).parent.parent / "alembic" / "env.py"


def _load_env_module(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """Load ``alembic/env.py`` as a module without executing ``run()``."""
    from alembic import context as real_context

    monkeypatch.setattr(real_context, "is_offline_mode", lambda: True)
    monkeypatch.setattr(real_context, "configure", lambda **_: None)

    fake_config = MagicMock()
    fake_config.config_file_name = None
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
    fake_settings.use_azure_postgres = False
    fake_settings.database_url = (
        "postgresql+asyncpg://postgres:postgres@db:5432/test_learn_to_cloud"
    )
    monkeypatch.setattr(env, "get_database_settings", lambda: fake_settings)

    url = env._get_sync_database_url()

    assert url.startswith("postgresql+psycopg2://")
    assert "+asyncpg" not in url
