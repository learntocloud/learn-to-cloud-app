resource "azurerm_storage_account" "verification_functions" {
  name                            = local.verification_functions_storage_account_name
  resource_group_name             = azurerm_resource_group.main.name
  location                        = azurerm_resource_group.main.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = false
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
  role_definition_name             = "Foundry User"
  principal_id                     = azurerm_user_assigned_identity.verification_functions.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}


# The Functions host and the deployment process both reach the storage account
# with the app's user-assigned identity, so no account key is ever issued.
# Blob Data Owner (not Contributor) is required: the host manages its own
# containers and takes blob leases for singleton coordination.
resource "azurerm_role_assignment" "verification_functions_storage_blob" {
  scope                            = azurerm_storage_account.verification_functions.id
  role_definition_name             = "Storage Blob Data Owner"
  principal_id                     = azurerm_user_assigned_identity.verification_functions.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "verification_functions_storage_queue" {
  scope                            = azurerm_storage_account.verification_functions.id
  role_definition_name             = "Storage Queue Data Contributor"
  principal_id                     = azurerm_user_assigned_identity.verification_functions.principal_id
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

locals {
  # AzureWebJobsStorage is configured with the identity-based __ properties
  # instead of a connection string, so no storage key exists in state or in the
  # app configuration. Secrets stay as Key Vault references, which the app
  # resolves with keyVaultReferenceIdentity.
  verification_functions_app_settings = {
    APPLICATIONINSIGHTS_CONNECTION_STRING       = azurerm_application_insights.main.connection_string
    AZURE_CLIENT_ID                             = azurerm_user_assigned_identity.verification_functions.client_id
    AzureWebJobsStorage__accountName            = azurerm_storage_account.verification_functions.name
    AzureWebJobsStorage__credential             = "managedidentity"
    AzureWebJobsStorage__clientId               = azurerm_user_assigned_identity.verification_functions.client_id
    DATABASE__URL                               = ""
    DATABASE__HOST                              = azurerm_postgresql_flexible_server.main.fqdn
    DATABASE__NAME                              = azurerm_postgresql_flexible_server_database.main.name
    DATABASE__USER                              = local.verification_functions_postgres_role
    DURABLE_TASK_SCHEDULER_CONNECTION_STRING    = "Endpoint=${azapi_resource.verification_scheduler.output.properties.endpoint};Authentication=ManagedIdentity;ClientID=${azurerm_user_assigned_identity.verification_functions.client_id}"
    ENABLE_INSTRUMENTATION                      = "true"
    ENABLE_SENSITIVE_DATA                       = "false"
    FOUNDRY_MODEL_DEPLOYMENT_NAME               = azapi_resource.foundry_model_deployment.name
    FOUNDRY_PROJECT_ENDPOINT                    = local.foundry_project_endpoint
    GITHUB__TOKEN                               = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=github-token)"
    LABS__VERIFICATION_SECRET                   = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=labs-verification-secret)"
    OAUTH__CLIENT_ID                            = var.github_client_id
    OAUTH__CLIENT_SECRET                        = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=github-client-secret)"
    OTEL_SERVICE_NAME                           = "learn-to-cloud-verification-functions"
    PYTHON_APPLICATIONINSIGHTS_ENABLE_TELEMETRY = "true"
    SESSION__SECRET_KEY                         = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=session-secret-key)"
    TASKHUB_NAME                                = local.verification_functions_task_hub_name
  }
}

# Modelled with azapi rather than azurerm_function_app_flex_consumption because
# that resource always derives the AzureWebJobsStorage setting from a key-based
# connection string, regardless of storage_authentication_type, and exposes no
# way to set keyVaultReferenceIdentity. See infra/CLEANUP.md.
resource "azapi_resource" "verification_functions" {
  type      = "Microsoft.Web/sites@2024-04-01"
  name      = "func-ltc-verification-${var.environment}"
  parent_id = azurerm_resource_group.main.id
  location  = azurerm_resource_group.main.location
  tags      = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.verification_functions.id]
  }

  body = {
    kind = "functionapp,linux"
    properties = {
      serverFarmId        = azurerm_service_plan.verification_functions.id
      httpsOnly           = true
      publicNetworkAccess = "Enabled"

      # Key Vault references resolve through the same identity the app runs as,
      # rather than the platform default of the system-assigned identity.
      keyVaultReferenceIdentity = azurerm_user_assigned_identity.verification_functions.id

      functionAppConfig = {
        deployment = {
          storage = {
            type  = "blobContainer"
            value = "${azurerm_storage_account.verification_functions.primary_blob_endpoint}${azurerm_storage_container.verification_functions_deployments.name}"
            authentication = {
              type                           = "UserAssignedIdentity"
              userAssignedIdentityResourceId = azurerm_user_assigned_identity.verification_functions.id
            }
          }
        }

        runtime = {
          name    = "python"
          version = "3.13"
        }

        scaleAndConcurrency = {
          instanceMemoryMB     = 2048
          maximumInstanceCount = 100
        }
      }

      siteConfig = {
        minTlsVersion    = "1.2"
        scmMinTlsVersion = "1.2"
        ftpsState        = "FtpsOnly"

        appSettings = [
          for name, value in local.verification_functions_app_settings : {
            name  = name
            value = value
          }
        ]
      }
    }
  }

  # ARM returns the service plan ID with different casing than it accepts.
  ignore_casing             = true
  response_export_values    = ["properties.defaultHostName"]
  schema_validation_enabled = false

  depends_on = [
    azurerm_role_assignment.verification_functions_durable_task,
    azurerm_role_assignment.verification_functions_foundry,
    azurerm_role_assignment.verification_functions_storage_blob,
    azurerm_role_assignment.verification_functions_storage_queue,
    azapi_resource.foundry_model_deployment,
    azurerm_postgresql_flexible_server_database.main,
  ]

  lifecycle {
    precondition {
      condition     = length(trimspace(local.verification_functions_auth_client_id)) > 0
      error_message = "verification_functions_auth_client_id must be set for this environment."
    }
  }
}

resource "azapi_resource" "verification_functions_auth" {
  type      = "Microsoft.Web/sites/config@2024-04-01"
  name      = "authsettingsV2"
  parent_id = azapi_resource.verification_functions.id

  body = {
    properties = {
      globalValidation = {
        requireAuthentication       = true
        unauthenticatedClientAction = "Return401"
      }

      httpSettings = {
        requireHttps = true
      }

      identityProviders = {
        azureActiveDirectory = {
          enabled = true
          registration = {
            clientId     = local.verification_functions_auth_client_id
            openIdIssuer = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
          }
          validation = {
            allowedAudiences = [
              local.verification_functions_auth_client_id,
              local.verification_functions_auth_audience,
            ]
            defaultAuthorizationPolicy = {
              allowedApplications = [
                azurerm_user_assigned_identity.api.client_id,
              ]
              allowedPrincipals = {
                identities = [
                  azurerm_user_assigned_identity.api.principal_id,
                ]
              }
            }
          }
        }
      }

      platform = {
        enabled        = true
        runtimeVersion = "~1"
      }
    }
  }

  schema_validation_enabled = false

  # ARM returns the parent site's tags on this child resource, but they cannot
  # be set here independently, so tracking them would cause perpetual drift.
  lifecycle {
    ignore_changes = [tags]
  }
}
