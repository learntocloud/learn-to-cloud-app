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

variables {
  subscription_id                     = "00000000-0000-0000-0000-000000000001"
  postgres_entra_admin_object_id      = "00000000-0000-0000-0000-000000000002"
  postgres_entra_admin_principal_name = "Learn to Cloud PostgreSQL Admins"
  github_client_id                    = "test-github-client-id"
}

run "secretless_planning_invariants" {
  command = plan

  plan_options {
    target = [
      azurerm_storage_account.verification_functions,
      azapi_resource.verification_functions,
    ]
  }

  assert {
    condition     = azurerm_storage_account.verification_functions.shared_access_key_enabled == false
    error_message = "The Functions storage account must keep Shared Key disabled."
  }

  assert {
    condition     = azapi_resource.verification_functions.body.properties.functionAppConfig.deployment.storage.authentication.type == "UserAssignedIdentity"
    error_message = "Function deployment storage must use the user-assigned identity."
  }

  assert {
    condition = !contains(
      [
        for setting in azapi_resource.verification_functions.body.properties.siteConfig.appSettings :
        setting.name
      ],
      "AzureWebJobsStorage",
    )
    error_message = "The Function App must not use a connection-string AzureWebJobsStorage setting."
  }

}
