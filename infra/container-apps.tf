# -----------------------------------------------------------------------------
# Container Registry
# -----------------------------------------------------------------------------
resource "azurerm_container_registry" "main" {
  name                = "crltc${local.suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = true
  tags                = local.tags
}

# -----------------------------------------------------------------------------
# Container Apps Environment
# -----------------------------------------------------------------------------
resource "azurerm_container_app_environment" "main" {
  name                       = "cae-ltc-${var.environment}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.tags
}

# -----------------------------------------------------------------------------
# API Container App
# -----------------------------------------------------------------------------
resource "azurerm_container_app" "api" {
  name                         = "ca-ltc-api-${var.environment}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.api.id]
  }

  registry {
    server               = azurerm_container_registry.main.login_server
    username             = azurerm_container_registry.main.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.main.admin_password
  }

  secret {
    name  = "github-client-secret"
    value = var.github_client_secret
  }

  secret {
    name  = "session-secret-key"
    value = var.session_secret_key
  }

  secret {
    name  = "ctf-master-secret"
    value = var.labs_verification_secret
  }

  secret {
    name  = "llm-api-key"
    value = azurerm_cognitive_account.openai.primary_access_key
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
    min_replicas = 1
    # B1ms PostgreSQL allows 35 user connections.
    # Each replica uses up to 10 (pool_size=5 + max_overflow=5).
    # 2 replicas × 10 = 20 connections — safely under the limit.
    # Scaling uses the default HTTP rule (10 concurrent requests per replica).
    max_replicas = 2

    # Migrations run inside the app lifespan (not an init container) because
    # Azure Container Apps init containers don't have access to the managed
    # identity sidecar needed for Entra ID database authentication.

    container {
      name   = "api"
      image  = "${azurerm_container_registry.main.login_server}/api:latest"
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "POSTGRES_HOST"
        value = azurerm_postgresql_flexible_server.main.fqdn
      }

      env {
        name  = "POSTGRES_USER"
        value = azurerm_user_assigned_identity.api.name
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
        name  = "LLM_BASE_URL"
        value = azurerm_cognitive_account.openai.endpoint
      }

      env {
        name        = "LLM_API_KEY"
        secret_name = "llm-api-key"
      }

      env {
        name  = "LLM_MODEL"
        value = var.llm_model
      }

      liveness_probe {
        transport               = "HTTP"
        path                    = "/health"
        port                    = 8000
        initial_delay           = 30
        interval_seconds        = 30
        timeout                 = 5
        failure_count_threshold = 3
      }

      readiness_probe {
        transport               = "HTTP"
        path                    = "/health"
        port                    = 8000
        interval_seconds        = 10
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
    azurerm_postgresql_flexible_server_database.main,
    azurerm_cognitive_deployment.llm,
  ]
}
