"""Alembic migrations bundled with the package, and the deploy-gate runner."""

from __future__ import annotations

from alembic import command
from alembic.config import Config

from learn_to_cloud.core.logger import configure_logging

SCRIPT_LOCATION = "learn_to_cloud:migrations"


def alembic_config() -> Config:
    """Return an Alembic config that resolves scripts from the installed package."""
    config = Config()
    config.set_main_option("script_location", SCRIPT_LOCATION)
    return config


def main() -> None:
    """Run the migration job's deploy gate.

    Upgrades to head, asserts the database is at the script head(s), then
    asserts the live schema matches ``Base.metadata``.
    """
    configure_logging()
    config = alembic_config()
    command.upgrade(config, "head")
    command.current(config, check_heads=True)
    command.check(config)
