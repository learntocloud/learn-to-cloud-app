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
    name  = "google-api-key"
    value = var.google_api_key
  }

  secret {
    name  = "ctf-master-secret"
    value = var.labs_verification_secret
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
    max_replicas = 3

    # -----------------------------------------------------------------------
    # Init container – runs Alembic migrations before the app starts.
    # Uses the same image and DB credentials as the main container.
    # -----------------------------------------------------------------------
    init_container {
      name   = "migrate"
      image  = "${azurerm_container_registry.main.login_server}/api:latest"
      cpu    = 0.25
      memory = "0.5Gi"

      command = ["python", "-m", "alembic", "upgrade", "head"]

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
        name  = "ENVIRONMENT"
        value = var.environment
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
    }

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
        name        = "GOOGLE_API_KEY"
        secret_name = "google-api-key"
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
        name  = "ENVIRONMENT"
        value = var.environment
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

  depends_on = [azurerm_postgresql_flexible_server_database.main]
}
