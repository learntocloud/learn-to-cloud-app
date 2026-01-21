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
    name  = "clerk-secret-key"
    value = var.clerk_secret_key
  }

  secret {
    name  = "clerk-webhook-secret"
    value = var.clerk_webhook_signing_secret
  }

  secret {
    name  = "google-api-key"
    value = var.google_api_key
  }

  secret {
    name  = "ctf-master-secret"
    value = var.ctf_master_secret
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

    container {
      name   = "api"
      image  = "${azurerm_container_registry.main.login_server}/api:v2"
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
        name  = "CLERK_PUBLISHABLE_KEY"
        value = var.clerk_publishable_key
      }

      env {
        name  = "CLERK_FAPI_BASE"
        value = var.clerk_fapi_base
      }

      env {
        name        = "CLERK_SECRET_KEY"
        secret_name = "clerk-secret-key"
      }

      env {
        name        = "CLERK_WEBHOOK_SIGNING_SECRET"
        secret_name = "clerk-webhook-secret"
      }

      env {
        name        = "GOOGLE_API_KEY"
        secret_name = "google-api-key"
      }

      env {
        name        = "CTF_MASTER_SECRET"
        secret_name = "ctf-master-secret"
      }

      env {
        name  = "SYNC_GRADING_CONCEPTS_ON_STARTUP"
        value = "true"
      }

      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.main.connection_string
      }

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }

      env {
        name  = "FRONTEND_URL"
        value = var.frontend_custom_domain != "" ? "https://${var.frontend_custom_domain}" : "https://${azurerm_static_web_app.frontend.default_host_name}"
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
