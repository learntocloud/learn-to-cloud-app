"""The browser-cookie generator must use the local committed session service."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
from learn_to_cloud_shared.core.config import DatabaseConfig, Environment
from learn_to_cloud_shared.models import AuthSession, User
from sqlalchemy.ext.asyncio import async_sessionmaker

from learn_to_cloud.core.session_cookies import AUTH_COOKIE_NAME, token_digest

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "dogfood_session.py"
_SPEC = importlib.util.spec_from_file_location("dogfood_session", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
dogfood = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(dogfood)


@pytest.mark.unit
@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "127.1.2.3", "[::1]"])
def test_accepts_loopback(test_settings, host):
    settings = test_settings.model_copy(
        update={
            "database": DatabaseConfig(
                url=f"postgresql+asyncpg://local:local@{host}:55432/test_learn_to_cloud"
            )
        }
    )
    dogfood.validate_local_target(settings)


@pytest.mark.unit
@pytest.mark.parametrize(
    "target",
    [
        "postgresql+asyncpg://u:p@db:5432/local",
        "postgresql+asyncpg://u:p@localhost.example.com/local",
        "postgresql+asyncpg://u:p@192.168.1.1/local",
        "postgresql+asyncpg://u:p@[::ffff:192.168.1.1]/local",
        "postgresql+asyncpg://u:p@localhost/local?host=remote",
        "postgresql+asyncpg://u:p@localhost/local?hostaddr=10.0.0.1",
        "postgresql+asyncpg://u:p@/local",
        "postgresql://u:p@localhost/local",
    ],
)
def test_refuses_remote_or_ambiguous_database(test_settings, target):
    settings = test_settings.model_copy(update={"database": DatabaseConfig(url=target)})
    with pytest.raises(ValueError, match="local|loopback"):
        dogfood.validate_local_target(settings)


@pytest.mark.unit
def test_refuses_production(test_settings):
    settings = test_settings.model_copy(update={"environment": Environment.PRODUCTION})
    with pytest.raises(ValueError, match="development"):
        dogfood.validate_local_target(settings)


@pytest.mark.integration
async def test_generator_persists_real_cookie_and_existing_user(
    test_engine, test_settings
):
    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    async with maker() as db, db.begin():
        db.add(User(id=42, github_username="madebygps"))
    result = await dogfood.generate_cookie(settings=test_settings)
    assert result["cookie_name"] == AUTH_COOKIE_NAME
    assert result["user_id"] == 42
    assert result["domain"] == "localhost"
    assert result["path"] == "/"
    async with maker() as db:
        row = await db.get(AuthSession, token_digest(result["cookie_value"]))
        assert row is not None
        assert row.user_id == 42


@pytest.mark.integration
async def test_missing_user_has_no_synthetic_fallback(test_engine, test_settings):
    with pytest.raises(ValueError, match="existing local account"):
        await dogfood.generate_cookie(999, settings=test_settings)


@pytest.mark.unit
async def test_database_failure_is_not_silenced(test_settings):
    with (
        patch.object(
            dogfood,
            "create_async_engine",
            side_effect=RuntimeError("database unavailable"),
        ),
        pytest.raises(RuntimeError, match="database unavailable"),
    ):
        await dogfood.generate_cookie(42, settings=test_settings)
