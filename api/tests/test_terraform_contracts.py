"""Static contracts for secretless Terraform planning."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).parents[2]


def test_api_container_app_refresh_does_not_use_azurerm():
    container_app = (_ROOT / "infra" / "container-apps.tf").read_text()

    assert 'resource "azapi_resource" "api"' in container_app
    assert 'resource "azurerm_container_app" "api' not in container_app
    assert "secrets = local.api_container_app_secrets" in container_app
    assert "keyVaultUrl" in container_app


def test_api_container_app_state_migration_preserves_the_live_resource():
    migration = (_ROOT / "infra" / "migrate-container-app-azapi.tf").read_text()

    assert "from = azurerm_container_app.api_v5" in migration
    assert "destroy = false" in migration
    assert "to = azapi_resource.api" in migration
