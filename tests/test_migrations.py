"""Tests for the packaged Alembic config and migration-job runner."""

from __future__ import annotations

from unittest.mock import call, patch

import pytest
from alembic.script import ScriptDirectory

from learn_to_cloud import migrations


@pytest.mark.unit
def test_alembic_config_resolves_packaged_scripts() -> None:
    script = ScriptDirectory.from_config(migrations.alembic_config())

    assert script.get_current_head() is not None


@pytest.mark.unit
def test_main_upgrades_then_verifies_heads_and_schema() -> None:
    with (
        patch.object(migrations, "configure_logging") as configure_logging,
        patch.object(migrations, "command") as command,
    ):
        migrations.main()

    configure_logging.assert_called_once_with()
    config = command.upgrade.call_args.args[0]
    assert command.mock_calls == [
        call.upgrade(config, "head"),
        call.current(config, check_heads=True),
        call.check(config),
    ]
