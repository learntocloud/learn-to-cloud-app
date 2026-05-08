resource "azurerm_storage_account" "verification_functions" {
  name                            = local.verification_functions_storage_account_name
  resource_group_name             = azurerm_resource_group.main.name
  location                        = azurerm_resource_group.main.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  allow_nested_items_to_be_public = false
  tags                            = local.tags
}

resource "azurerm_storage_container" "verification_functions_deployments" {
  name                  = "function-releases"
  storage_account_id    = azurerm_storage_account.verification_functions.id
  container_access_type = "private"
}

resource "azurerm_service_plan" "verification_functions" {
  name                = "plan-ltc-verification-functions-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Linux"
  sku_name            = "FC1"
  tags                = local.tags
}

resource "azapi_resource" "verification_scheduler" {
  type      = "Microsoft.DurableTask/schedulers@2025-04-01-preview"
  name      = "dts-ltc-verification-${var.environment}-${local.suffix}"
  parent_id = azurerm_resource_group.main.id
  location  = azurerm_resource_group.main.location
  tags      = local.tags

  body = {
    properties = {
      ipAllowlist = var.durable_task_scheduler_ip_allowlist
      sku = {
        name = "Consumption"
      }
    }
  }

  response_export_values    = ["properties.endpoint"]
  schema_validation_enabled = false

  lifecycle {
    precondition {
      condition = var.environment != "prod" || (
        !contains(var.durable_task_scheduler_ip_allowlist, "0.0.0.0/0") &&
        !contains(var.durable_task_scheduler_ip_allowlist, "::/0")
      )
      error_message = "durable_task_scheduler_ip_allowlist must not allow all IPv4 or IPv6 addresses in prod."
    }
  }
}

resource "azapi_resource" "verification_task_hub" {
  type      = "Microsoft.DurableTask/schedulers/taskHubs@2025-04-01-preview"
  name      = local.verification_functions_task_hub_name
  parent_id = azapi_resource.verification_scheduler.id

  body = {
    properties = {}
  }

  schema_validation_enabled = false
}

resource "azurerm_role_assignment" "verification_functions_durable_task" {
  scope                            = azapi_resource.verification_task_hub.id
  role_definition_name             = "Durable Task Data Contributor"
  principal_id                     = azurerm_user_assigned_identity.verification_functions.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "verification_task_hub_dashboard_readers" {
  for_each = toset(lookup(var.durable_task_dashboard_reader_group_object_ids_by_environment, var.environment, []))

  scope                = azapi_resource.verification_task_hub.id
  role_definition_name = "Durable Task Data Reader"
  principal_id         = each.value
  principal_type       = "Group"
}

resource "azurerm_role_assignment" "verification_functions_foundry" {
  scope                            = azapi_resource.foundry_project.id
  role_definition_name             = "Azure AI User"
  principal_id                     = azurerm_user_assigned_identity.verification_functions.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_function_app_flex_consumption" "verification" {
  name                = "func-ltc-verification-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  service_plan_id     = azurerm_service_plan.verification_functions.id
  https_only          = true
  tags                = local.tags

  storage_container_type      = "blobContainer"
  storage_container_endpoint  = "${azurerm_storage_account.verification_functions.primary_blob_endpoint}${azurerm_storage_container.verification_functions_deployments.name}"
  storage_authentication_type = "StorageAccountConnectionString"
  storage_access_key          = azurerm_storage_account.verification_functions.primary_access_key
  runtime_name                = "python"
  runtime_version             = "3.13"

  identity {
    type         = "SystemAssigned, UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.verification_functions.id]
  }

  app_settings = {
    AZURE_CLIENT_ID                          = azurerm_user_assigned_identity.verification_functions.client_id
    DATABASE_URL                             = ""
    ENABLE_INSTRUMENTATION                   = "true"
    DURABLE_TASK_SCHEDULER_CONNECTION_STRING = "Endpoint=${azapi_resource.verification_scheduler.output.properties.endpoint};Authentication=ManagedIdentity;ClientID=${azurerm_user_assigned_identity.verification_functions.client_id}"
    GITHUB_CLIENT_ID                         = var.github_client_id
    GITHUB_CLIENT_SECRET                     = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=github-client-secret)"
    GITHUB_TOKEN                             = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=github-token)"
    FOUNDRY_MODEL_DEPLOYMENT_NAME            = azapi_resource.foundry_model_deployment.name
    FOUNDRY_PROJECT_ENDPOINT                 = local.foundry_project_endpoint
    LABS_VERIFICATION_SECRET                 = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=labs-verification-secret)"
    OTEL_SERVICE_NAME                        = "learn-to-cloud-verification-functions"
    POSTGRES_DATABASE                        = azurerm_postgresql_flexible_server_database.main.name
    POSTGRES_HOST                            = azurerm_postgresql_flexible_server.main.fqdn
    POSTGRES_USER                            = local.verification_functions_postgres_role
    SESSION_SECRET_KEY                       = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=session-secret-key)"
    TASKHUB_NAME                             = local.verification_functions_task_hub_name
  }

  site_config {
    application_insights_connection_string = azurerm_application_insights.main.connection_string
    minimum_tls_version                    = "1.2"
  }

  depends_on = [
    azurerm_role_assignment.verification_functions_durable_task,
    azurerm_role_assignment.verification_functions_foundry,
    azapi_resource.foundry_model_deployment,
    azurerm_postgresql_flexible_server_database.main,
  ]
}

data "azurerm_function_app_host_keys" "verification" {
  name                = azurerm_function_app_flex_consumption.verification.name
  resource_group_name = azurerm_resource_group.main.name

  depends_on = [azurerm_function_app_flex_consumption.verification]
}
