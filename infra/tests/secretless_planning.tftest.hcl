mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      client_id       = "00000000-0000-0000-0000-000000000003"
      object_id       = "00000000-0000-0000-0000-000000000004"
      subscription_id = "00000000-0000-0000-0000-000000000001"
      tenant_id       = "00000000-0000-0000-0000-000000000005"
    }
  }

  mock_resource "azurerm_resource_group" {
    override_during = plan
    defaults = {
      id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-ltc-dev"
    }
  }
}
mock_provider "azapi" {}
mock_provider "random" {}

run "session_migration_runtime_grant" {
  command = plan

  variables {
    postgres_api_runtime_role = "custom_api_runtime"
  }

  plan_options {
    target = [azapi_resource.migrations]
  }

  assert {
    condition = one([
      for setting in azapi_resource.migrations.body.properties.template.containers[0].env :
      setting.value if setting.name == "POSTGRES_API_RUNTIME_ROLE"
    ]) == "custom_api_runtime"
    error_message = "Session migrations must grant DML to the configured API runtime role."
  }
}

variables {
  subscription_id                     = "00000000-0000-0000-0000-000000000001"
  postgres_entra_admin_object_id      = "00000000-0000-0000-0000-000000000002"
  postgres_entra_admin_principal_name = "Learn to Cloud PostgreSQL Admins"
  github_client_id                    = "test-github-client-id"
}

run "api_verification_worker" {
  command = plan

  plan_options {
    target = [
      azurerm_container_app.api_v5,
    ]
  }

  assert {
    condition     = azurerm_container_app.api_v5.template[0].min_replicas == 1
    error_message = "The API must keep a replica running to poll verification attempts."
  }

  assert {
    condition     = azurerm_container_app.api_v5.template[0].max_replicas == 2
    error_message = "API scaling must default to at most two replicas."
  }

  assert {
    condition = (
      azurerm_container_app.api_v5.template[0].container[0].cpu == 0.25 &&
      azurerm_container_app.api_v5.template[0].container[0].memory == "0.5Gi"
    )
    error_message = "The worker must preserve the existing API CPU and memory allocation."
  }

  assert {
    condition = one([
      for setting in azurerm_container_app.api_v5.template[0].container[0].env :
      setting.value if setting.name == "FOUNDRY_MODEL_DEPLOYMENT_NAME"
    ]) == var.foundry_model_deployment_name
    error_message = "The API worker must use the configured Foundry deployment."
  }

  assert {
    condition     = azurerm_role_assignment.api_foundry.role_definition_name == "Foundry User"
    error_message = "The API identity must be granted Foundry User."
  }
}
