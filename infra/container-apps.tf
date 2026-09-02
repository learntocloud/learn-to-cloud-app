resource "azurerm_container_registry" "main" {
  name                = "crltc${local.suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = false
  tags                = local.tags
}

resource "azurerm_role_assignment" "api_acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.api.principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "migrations_acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.migrations.principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_container_app_environment" "main" {
  name                       = "cae-ltc-${var.environment}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  logs_destination           = "log-analytics"
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.tags
}

locals {
  api_container_app_api_version   = "2025-01-01"
  api_container_app_resource_type = "Microsoft.App/containerApps@${local.api_container_app_api_version}"
  api_container_app_secrets = [
    {
      name        = "github-client-secret"
      identity    = azurerm_user_assigned_identity.api.id
      keyVaultUrl = "${azurerm_key_vault.main.vault_uri}secrets/github-client-secret"
    },
    {
      name        = "github-token"
      identity    = azurerm_user_assigned_identity.api.id
      keyVaultUrl = "${azurerm_key_vault.main.vault_uri}secrets/github-token"
    },
    {
      name        = "session-secret-key"
      identity    = azurerm_user_assigned_identity.api.id
      keyVaultUrl = "${azurerm_key_vault.main.vault_uri}secrets/session-secret-key"
    },
    {
      name        = "ctf-master-secret"
      identity    = azurerm_user_assigned_identity.api.id
      keyVaultUrl = "${azurerm_key_vault.main.vault_uri}secrets/labs-verification-secret"
    },
  ]
}

# Preserve custom-domain bindings that are currently managed outside Terraform.
# The normal ARM GET used here does not require the secret-reading action that
# AzureRM invokes during every Container App refresh.
data "azapi_resource" "api_current" {
  type             = local.api_container_app_resource_type
  name             = "ca-ltc-api-${var.environment}"
  parent_id        = azurerm_resource_group.main.id
  ignore_not_found = true

  response_export_values = ["properties.configuration.ingress.customDomains"]
}

resource "azapi_resource" "api" {
  type      = local.api_container_app_resource_type
  name      = "ca-ltc-api-${var.environment}"
  parent_id = azurerm_resource_group.main.id
  location  = azurerm_resource_group.main.location
  tags      = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.api.id]
  }

  body = {
    properties = {
      managedEnvironmentId = azurerm_container_app_environment.main.id

      configuration = {
        activeRevisionsMode = "Single"
        registries = [
          {
            server   = azurerm_container_registry.main.login_server
            identity = azurerm_user_assigned_identity.api.id
          },
        ]
        secrets = local.api_container_app_secrets
        ingress = {
          allowInsecure = false
          external      = true
          targetPort    = 8000
          transport     = "Http"
          customDomains = try(
            data.azapi_resource.api_current.output.properties.configuration.ingress.customDomains,
            [],
          )
          traffic = [
            {
              latestRevision = true
              weight         = 100
            },
          ]
        }
      }

      template = {
        scale = {
          minReplicas = local.api_min_replicas
          # PostgreSQL max connections vary by SKU. Each replica uses up to 10
          # connections, so the default two replicas remain well within limits.
          maxReplicas = local.api_max_replicas
        }
        containers = [
          {
            name  = "api"
            image = "${azurerm_container_registry.main.login_server}/api:latest"
            env = [
              {
                name  = "DATABASE__HOST"
                value = azurerm_postgresql_flexible_server.main.fqdn
              },
              {
                name  = "DATABASE__USER"
                value = local.api_postgres_role
              },
              {
                name  = "DATABASE__NAME"
                value = azurerm_postgresql_flexible_server_database.main.name
              },
              {
                name  = "AZURE_CLIENT_ID"
                value = azurerm_user_assigned_identity.api.client_id
              },
              {
                name  = "OAUTH__CLIENT_ID"
                value = var.github_client_id
              },
              {
                name      = "OAUTH__CLIENT_SECRET"
                secretRef = "github-client-secret"
              },
              {
                name      = "GITHUB__TOKEN"
                secretRef = "github-token"
              },
              {
                name      = "SESSION__SECRET_KEY"
                secretRef = "session-secret-key"
              },
              {
                name      = "LABS__VERIFICATION_SECRET"
                secretRef = "ctf-master-secret"
              },
              {
                name  = "SMOKE_TEST__ALLOWED_CLIENT_ID"
                value = local.smoke_auth_allowed_client_id
              },
              {
                name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
                value = azurerm_application_insights.main.connection_string
              },
              {
                name  = "FRONTEND_TELEMETRY__APPLICATIONINSIGHTS_CONNECTION_STRING"
                value = azurerm_application_insights.frontend.connection_string
              },
              {
                name  = "OTEL_SERVICE_NAME"
                value = "learn-to-cloud-api"
              },
              {
                name  = "OTEL_TRACES_SAMPLER"
                value = "microsoft.rate_limited"
              },
              {
                name  = "OTEL_TRACES_SAMPLER_ARG"
                value = "1"
              },
              {
                name  = "VERIFICATION_FUNCTIONS__BASE_URL"
                value = "https://${azapi_resource.verification_functions.output.properties.defaultHostName}"
              },
              {
                name  = "VERIFICATION_FUNCTIONS__TOKEN_SCOPE"
                value = local.verification_functions_auth_scope
              },
              {
                name  = "CORS__FRONTEND_URL"
                value = "https://learntocloud.guide"
              },
            ]
            probes = [
              {
                type                = "Liveness"
                initialDelaySeconds = 30
                periodSeconds       = 60
                timeoutSeconds      = 5
                failureThreshold    = 3
                httpGet = {
                  path   = "/health"
                  port   = 8000
                  scheme = "HTTP"
                }
              },
              {
                type             = "Readiness"
                periodSeconds    = 30
                timeoutSeconds   = 5
                failureThreshold = 3
                successThreshold = 3
                httpGet = {
                  path   = "/ready"
                  port   = 8000
                  scheme = "HTTP"
                }
              },
              {
                type             = "Startup"
                periodSeconds    = 10
                timeoutSeconds   = 5
                failureThreshold = 30
                httpGet = {
                  path   = "/ready"
                  port   = 8000
                  scheme = "HTTP"
                }
              },
            ]
            resources = {
              cpu    = 0.25
              memory = "0.5Gi"
            }
          },
        ]
      }
    }
  }

  response_export_values = ["properties.configuration.ingress.fqdn"]

  lifecycle {
    ignore_changes = [
      body.properties.template.containers[0].image,
    ]

    precondition {
      condition     = local.api_min_replicas <= local.api_max_replicas
      error_message = "api_min_replicas must be less than or equal to api_max_replicas."
    }

    precondition {
      condition = alltrue([
        for secret in local.api_container_app_secrets :
        can(secret.keyVaultUrl) && !can(secret.value)
      ])
      error_message = "API Container App secrets must use Key Vault references, not inline values."
    }
  }

  depends_on = [
    azurerm_role_assignment.api_acr_pull,
    azurerm_role_assignment.api_key_vault_secrets_user,
  ]
}

# The app remains public, but Easy Auth validates any bearer token presented to
# it and strips client-supplied identity headers. The smoke route then requires
# the validated deployment identity and its Smoke.Trigger app role.
resource "azapi_resource" "api_auth" {
  type      = "Microsoft.App/containerApps/authConfigs@2025-01-01"
  name      = "current"
  parent_id = azapi_resource.api.id

  body = {
    properties = {
      globalValidation = {
        unauthenticatedClientAction = "AllowAnonymous"
      }

      httpSettings = {
        requireHttps = true
      }

      identityProviders = {
        azureActiveDirectory = {
          enabled = true
          registration = {
            clientId     = local.smoke_auth_client_id
            openIdIssuer = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
          }
          validation = {
            allowedAudiences = [
              local.smoke_auth_client_id,
              local.smoke_auth_audience,
            ]
            defaultAuthorizationPolicy = {
              allowedApplications = [
                local.smoke_auth_allowed_client_id,
              ]
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

  lifecycle {
    precondition {
      condition = (
        length(trimspace(local.smoke_auth_client_id)) > 0
        && length(trimspace(local.smoke_auth_allowed_client_id)) > 0
      )
      error_message = "Smoke-test Entra client IDs must be configured for this environment."
    }
  }
}
