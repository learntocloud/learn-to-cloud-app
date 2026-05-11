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
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.tags
}

resource "azurerm_container_app" "api" {
  name                         = "ca-ltc-api-${var.environment}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.tags

  lifecycle {
    ignore_changes = [
      template[0].container[0].image,
    ]

    precondition {
      condition     = local.api_min_replicas <= local.api_max_replicas
      error_message = "api_min_replicas must be less than or equal to api_max_replicas."
    }

  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.api.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.api.id
  }

  secret {
    name                = "github-client-secret"
    identity            = azurerm_user_assigned_identity.api.id
    key_vault_secret_id = "${azurerm_key_vault.main.vault_uri}secrets/github-client-secret"
  }

  secret {
    name                = "github-token"
    identity            = azurerm_user_assigned_identity.api.id
    key_vault_secret_id = "${azurerm_key_vault.main.vault_uri}secrets/github-token"
  }

  secret {
    name                = "session-secret-key"
    identity            = azurerm_user_assigned_identity.api.id
    key_vault_secret_id = "${azurerm_key_vault.main.vault_uri}secrets/session-secret-key"
  }

  secret {
    name                = "ctf-master-secret"
    identity            = azurerm_user_assigned_identity.api.id
    key_vault_secret_id = "${azurerm_key_vault.main.vault_uri}secrets/labs-verification-secret"
  }

  secret {
    name  = "verification-functions-key"
    value = data.azurerm_function_app_host_keys.verification.default_function_key
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "http"

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = local.api_min_replicas
    # PostgreSQL max connections vary by SKU.
    # Each replica uses up to 10 (pool_size=5 + max_overflow=5).
    # 2 replicas × 10 = 20 connections — well under typical SKU limits.
    # Scaling uses the default HTTP rule (10 concurrent requests per replica).
    max_replicas = local.api_max_replicas

    container {
      name   = "api"
      image  = "${azurerm_container_registry.main.login_server}/api:latest"
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "POSTGRES_HOST"
        value = azurerm_postgresql_flexible_server.main.fqdn
      }

      env {
        name  = "POSTGRES_USER"
        value = local.api_postgres_role
      }

      env {
        name  = "POSTGRES_DATABASE"
        value = azurerm_postgresql_flexible_server_database.main.name
      }

      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.api.client_id
      }

      env {
        name  = "GITHUB_CLIENT_ID"
        value = var.github_client_id
      }

      env {
        name        = "GITHUB_CLIENT_SECRET"
        secret_name = "github-client-secret"
      }

      env {
        name        = "GITHUB_TOKEN"
        secret_name = "github-token"
      }

      env {
        name        = "SESSION_SECRET_KEY"
        secret_name = "session-secret-key"
      }

      env {
        name        = "LABS_VERIFICATION_SECRET"
        secret_name = "ctf-master-secret"
      }

      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.main.connection_string
      }

      env {
        name  = "FRONTEND_APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.frontend.connection_string
      }

      env {
        name  = "OTEL_SERVICE_NAME"
        value = "learn-to-cloud-api"
      }

      env {
        name  = "VERIFICATION_FUNCTIONS_BASE_URL"
        value = "https://${azurerm_function_app_flex_consumption.verification.default_hostname}"
      }

      env {
        name        = "VERIFICATION_FUNCTIONS_KEY"
        secret_name = "verification-functions-key"
      }

      env {
        name  = "FRONTEND_URL"
        value = "https://learntocloud.guide"
      }

      liveness_probe {
        transport               = "HTTP"
        path                    = "/health"
        port                    = 8000
        initial_delay           = 30
        interval_seconds        = 60
        timeout                 = 5
        failure_count_threshold = 3
      }

      readiness_probe {
        transport               = "HTTP"
        path                    = "/health"
        port                    = 8000
        interval_seconds        = 30
        timeout                 = 5
        failure_count_threshold = 3
      }

      startup_probe {
        transport               = "HTTP"
        path                    = "/health"
        port                    = 8000
        interval_seconds        = 10
        timeout                 = 5
        failure_count_threshold = 30
      }
    }
  }

  depends_on = [
    azurerm_role_assignment.api_acr_pull,
    azurerm_role_assignment.api_key_vault_secrets_user,
    azurerm_postgresql_flexible_server_database.main,
  ]
}
