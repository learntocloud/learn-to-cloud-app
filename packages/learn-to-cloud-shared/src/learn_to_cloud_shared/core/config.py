"""Application configuration split by runtime profile.

The codebase has three deployable processes with very different needs:

* ``DatabaseSettings`` — minimal set for processes that only need DB
  access (the Alembic migration job, ad-hoc scripts).
* ``WorkerSettings`` — adds GitHub token, external API timeouts, and the
  labs verification secret. Used by the Verification Functions worker.
* ``WebSettings`` — adds GitHub OAuth, session secret, CORS, docs, and
  rate-limit config. Used by the FastAPI webapp.

Each entry-point should call :func:`configure_settings` with the most
specific class it needs before the first ``get_*_settings()`` call::

    # api/alembic/env.py
    configure_settings(DatabaseSettings)

    # apps/verification-functions/function_app.py
    configure_settings(WorkerSettings)

    # api/src/learn_to_cloud/main.py — implicit (WebSettings is the default)

Validation is enforced at construction time based on the
``Environment`` enum. In ``production`` the webapp requires GitHub OAuth
credentials and a non-default session secret; in ``development`` (used
by local dev, the dog-food agent, and tests) both checks relax so the
app starts without contributor-specific OAuth registrations.
"""

from __future__ import annotations

from enum import StrEnum
from functools import cached_property
from importlib.resources import files
from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Runtime environment for the webapp.

    ``development`` relaxes web-specific validation so local dev and the
    dog-food agent can run without contributor-specific OAuth credentials
    or a custom session secret. ``production`` enforces both strictly.
    """

    DEVELOPMENT = "development"
    PRODUCTION = "production"


_DEV_SESSION_SECRET = "dev-secret-key-change-in-production"


class DatabaseSettings(BaseSettings):
    """Minimal settings for DB-only processes (alembic, migration job)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    database_url: str = ""

    # Azure PostgreSQL with Managed Identity — takes precedence over database_url
    postgres_host: str = ""
    postgres_port: int = 5432
    postgres_database: str = "learntocloud"
    postgres_user: str = ""

    # Connection pool + timeouts.
    # Total connections per worker = pool_size + max_overflow.
    db_timeout: int = 30
    db_pool_size: int = 5
    db_pool_max_overflow: int = 5
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_statement_timeout_ms: int = 10000
    db_echo: bool = False

    @model_validator(mode="after")
    def _validate_database(self) -> Self:
        if not self.database_url and not self.use_azure_postgres:
            raise ValueError(
                "Database configuration required. "
                "Set DATABASE_URL for direct connection, "
                "or POSTGRES_HOST + POSTGRES_USER for Azure Managed Identity."
            )
        return self

    @property
    def use_azure_postgres(self) -> bool:
        """When True, connection is built from postgres_* fields."""
        return bool(self.postgres_host and self.postgres_user)


class WorkerSettings(DatabaseSettings):
    """Settings for background workers (Verification Functions).

    Adds GitHub server-to-server token, external API timeouts, the labs
    verification secret, and content path resolution. No web/OAuth/session
    concerns — workers never serve user requests.
    """

    github_token: str = ""
    labs_verification_secret: str = ""
    external_api_timeout: float = 15.0
    content_dir: str = ""

    @cached_property
    def content_dir_path(self) -> Path:
        """Resolve authored curriculum YAML for sync and validation jobs."""
        if self.content_dir:
            return Path(self.content_dir)

        source_content = Path(
            str(files("learn_to_cloud_shared").joinpath("content", "phases"))
        )
        if source_content.exists():
            return source_content

        raise RuntimeError(
            "CONTENT_DIR is required because curriculum YAML is not packaged "
            "with learn-to-cloud-shared. Set CONTENT_DIR to the copied "
            "content/phases directory in jobs that sync or validate YAML."
        )


class WebSettings(WorkerSettings):
    """Full settings for the FastAPI webapp.

    Adds OAuth, session, CORS, docs, rate-limit, and frontend telemetry
    config. Validation enforces production hardening: GitHub OAuth must
    be configured and the session secret must not be the dev default
    whenever ``environment == production``.
    """

    environment: Environment = Environment.PRODUCTION

    github_client_id: str = ""
    github_client_secret: str = ""

    session_secret_key: str = _DEV_SESSION_SECRET

    cors_allowed_origins: str = ""
    frontend_url: str = "http://localhost:4280"
    frontend_applicationinsights_connection_string: str = ""
    frontend_telemetry_sampling_percentage: float = Field(
        default=100.0, ge=0.0, le=100.0
    )

    startup_timeout: int = 60
    verification_wait_timeout: int = 180

    verification_functions_base_url: str = ""
    verification_functions_key: str = ""

    # memory:// only works for single-instance deployments
    ratelimit_storage_uri: str = "memory://"

    require_https: bool = True
    enable_docs: bool = False

    @model_validator(mode="after")
    def _validate_web(self) -> Self:
        if self.environment is Environment.PRODUCTION:
            if not self.github_client_id or not self.github_client_secret:
                raise ValueError(
                    "GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET must be set "
                    "when ENVIRONMENT=production."
                )
            if (
                not self.session_secret_key
                or self.session_secret_key == _DEV_SESSION_SECRET
            ):
                raise ValueError(
                    "SESSION_SECRET_KEY must be set to a secure random value "
                    "when ENVIRONMENT=production."
                )
        return self

    @property
    def is_development(self) -> bool:
        return self.environment is Environment.DEVELOPMENT

    @cached_property
    def allowed_origins(self) -> list[str]:
        """Combines localhost (dev only), frontend_url, and cors_allowed_origins."""
        origins: list[str] = []

        if self.is_development:
            origins.extend(
                [
                    "http://localhost:3000",
                    "http://localhost:4280",
                ]
            )

        if self.frontend_url and self.frontend_url not in origins:
            origins.append(self.frontend_url)

        if self.cors_allowed_origins:
            for origin in self.cors_allowed_origins.split(","):
                origin = origin.strip()
                if origin and origin not in origins:
                    origins.append(origin)

        return origins


# ---------------------------------------------------------------------------
# Registry — entry-points pick the most specific class their process needs;
# shared modules pull via the typed accessors below.
# ---------------------------------------------------------------------------


_registered_class: type[DatabaseSettings] = WebSettings
_instance: DatabaseSettings | None = None


def configure_settings(cls: type[DatabaseSettings]) -> None:
    """Bind the Settings subclass for this process.

    Must be called at process startup, before the first ``get_*_settings``
    call. Idempotent when the existing instance already satisfies ``cls``
    (e.g. a WebSettings instance satisfies a DatabaseSettings request via
    inheritance). Raises only when the requested class is MORE specific
    than the constructed instance, which would require validation the
    instance never ran.
    """
    global _registered_class, _instance
    if _instance is not None and not isinstance(_instance, cls):
        raise RuntimeError(
            f"configure_settings({cls.__name__}) called after "
            f"{type(_instance).__name__} was already constructed. "
            "Call clear_settings_cache() first if reconfiguration is intentional."
        )
    _registered_class = cls


def get_database_settings() -> DatabaseSettings:
    """Return the active settings, typed as the minimal ``DatabaseSettings``.

    Safe to call from any process: every supported settings class derives
    from ``DatabaseSettings``.
    """
    global _instance
    if _instance is None:
        _instance = _registered_class()
    return _instance


def get_worker_settings() -> WorkerSettings:
    """Return the active settings, typed as ``WorkerSettings``.

    Raises if the process configured only ``DatabaseSettings`` — the
    caller is asking for fields a DB-only profile doesn't have.
    """
    settings = get_database_settings()
    if not isinstance(settings, WorkerSettings):
        raise RuntimeError(
            "WorkerSettings requested but process is configured with "
            f"{type(settings).__name__}. Call configure_settings(WorkerSettings) "
            "before the first get_*_settings() call."
        )
    return settings


def get_web_settings() -> WebSettings:
    """Return the active settings, typed as ``WebSettings``.

    Raises if the process is not configured with ``WebSettings``. Webapp
    code calls this directly so the static type ``WebSettings`` flows
    through every access — fields the worker or DB profiles lack become
    type errors at the call site instead of runtime ``AttributeError``.
    """
    settings = get_database_settings()
    if not isinstance(settings, WebSettings):
        raise RuntimeError(
            "WebSettings requested but process is configured with "
            f"{type(settings).__name__}. Call configure_settings(WebSettings) "
            "before the first get_*_settings() call."
        )
    return settings


def clear_settings_cache() -> None:
    """Reset the cached settings instance.

    Tests use this to swap settings between cases. After clearing, the
    next ``get_*_settings()`` call constructs a fresh instance of the
    currently-registered class.
    """
    global _instance
    _instance = None
