# Container Apps Module: Environment, API, and Frontend
# Updated for Azure Provider v4.x

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

locals {
  api_app_name      = "ca-${var.app_name}-api-${var.environment}"
  frontend_app_name = "ca-${var.app_name}-frontend-${var.environment}"

  # CORS allowed origins
  api_cors_allowed_origins = var.frontend_custom_domain != "" ? [
    "https://*.azurecontainerapps.io",
    "http://localhost:3000",
    "https://${var.frontend_custom_domain}"
  ] : [
    "https://*.azurecontainerapps.io",
    "http://localhost:3000"
  ]
}

# Container Apps Environment
resource "azurerm_container_app_environment" "main" {
  name                = "cae-${var.app_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name

  log_analytics_workspace_id = var.log_analytics_workspace_id

  tags = var.tags
}

# Note: Managed certificates for custom domains are created outside Terraform via Azure CLI
# The custom domain binding is handled through the ingress block below

# API Container App (FastAPI)
resource "azurerm_container_app" "api" {
  name                         = local.api_app_name
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"

  identity {
    type = "SystemAssigned, UserAssigned"
    identity_ids = [
      var.user_assigned_identity_id
    ]
  }

  registry {
    server   = var.container_registry_login_server
    identity = "system"
  }

  secret {
    name                = "clerk-secret-key"
    key_vault_secret_id = var.clerk_secret_key_kv_id
    identity            = var.user_assigned_identity_id
  }

  secret {
    name                = "clerk-webhook-signing-secret"
    key_vault_secret_id = var.clerk_webhook_signing_secret_kv_id
    identity            = var.user_assigned_identity_id
  }

  dynamic "secret" {
    for_each = var.redis_connection_string_kv_id != null ? [1] : []
    content {
      name                = "redis-connection-string"
      key_vault_secret_id = var.redis_connection_string_kv_id
      identity            = var.user_assigned_identity_id
    }
  }

  dynamic "secret" {
    for_each = var.google_api_key_kv_id != null ? [1] : []
    content {
      name                = "google-api-key"
      key_vault_secret_id = var.google_api_key_kv_id
      identity            = var.user_assigned_identity_id
    }
  }

  template {
    min_replicas = 1 # Keep 1 instance always running to avoid cold starts
    max_replicas = 10

    http_scale_rule {
      name                = "http-scaling"
      concurrent_requests = "50" # Scale up sooner for better latency
    }

    container {
      name   = "api"
      image  = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "POSTGRES_HOST"
        value = var.postgres_fqdn
      }

      env {
        name  = "POSTGRES_DATABASE"
        value = "learntocloud"
      }

      env {
        name  = "POSTGRES_USER"
        value = local.api_app_name # Use managed identity name for Entra auth
      }

      env {
        name        = "CLERK_SECRET_KEY"
        secret_name = "clerk-secret-key"
      }

      env {
        name        = "CLERK_WEBHOOK_SIGNING_SECRET"
        secret_name = "clerk-webhook-signing-secret"
      }

      env {
        name  = "CLERK_PUBLISHABLE_KEY"
        value = var.clerk_publishable_key
      }

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }

      env {
        name  = "FRONTEND_URL"
        value = var.frontend_custom_domain != "" ? "https://${var.frontend_custom_domain}" : "https://${local.frontend_app_name}.${azurerm_container_app_environment.main.default_domain}"
      }

      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = var.app_insights_connection_string
      }

      dynamic "env" {
        for_each = var.redis_connection_string_kv_id != null ? [1] : []
        content {
          name        = "REDIS_URL"
          secret_name = "redis-connection-string"
        }
      }

      dynamic "env" {
        for_each = var.google_api_key_kv_id != null ? [1] : []
        content {
          name        = "GOOGLE_API_KEY"
          secret_name = "google-api-key"
        }
      }

      # Startup probe - allow longer startup for cold starts
      startup_probe {
        transport              = "HTTP"
        path                   = "/health"
        port                   = 8000
        initial_delay          = 5
        interval_seconds       = 10
        failure_count_threshold = 30 # Allow up to 5 minutes for cold start
        timeout                = 3
      }

      # Liveness probe
      liveness_probe {
        transport              = "HTTP"
        path                   = "/health"
        port                   = 8000
        initial_delay          = 0
        interval_seconds       = 30
        failure_count_threshold = 3
        timeout                = 5
      }

      # Readiness probe
      readiness_probe {
        transport              = "HTTP"
        path                   = "/ready"
        port                   = 8000
        initial_delay          = 0
        interval_seconds       = 10
        failure_count_threshold = 3
        timeout                = 3
      }
    }
  }

  ingress {
    external_enabled           = true
    target_port                = 8000
    transport                  = "http"
    allow_insecure_connections = false

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }

    cors {
      allowed_origins           = local.api_cors_allowed_origins
      allowed_methods           = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
      allowed_headers           = ["*"]
      exposed_headers           = []
      allow_credentials_enabled = true
      max_age_in_seconds        = 0
    }
  }

  tags = merge(var.tags, {
    "azd-service-name" = "api"
  })

  lifecycle {
    ignore_changes = [
      # Ignore image changes as these are managed by azd deploy
      template[0].container[0].image,
    ]
  }
}

# Frontend Container App (Next.js)
resource "azurerm_container_app" "frontend" {
  name                         = local.frontend_app_name
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"

  identity {
    type = "SystemAssigned, UserAssigned"
    identity_ids = [
      var.user_assigned_identity_id
    ]
  }

  registry {
    server   = var.container_registry_login_server
    identity = "system"
  }

  secret {
    name                = "clerk-secret-key"
    key_vault_secret_id = var.clerk_secret_key_kv_id
    identity            = var.user_assigned_identity_id
  }

  template {
    min_replicas = 0 # Scale to zero when idle (frontend cold starts are acceptable)
    max_replicas = 10

    http_scale_rule {
      name                = "http-scaling"
      concurrent_requests = "50"
    }

    container {
      name   = "frontend"
      image  = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "NEXT_PUBLIC_API_URL"
        value = "https://${azurerm_container_app.api.ingress[0].fqdn}"
      }

      env {
        name  = "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"
        value = var.clerk_publishable_key
      }

      env {
        name        = "CLERK_SECRET_KEY"
        secret_name = "clerk-secret-key"
      }

      env {
        name  = "PORT"
        value = "3000"
      }

      env {
        name  = "NEXT_PUBLIC_CLERK_SIGN_IN_URL"
        value = "/sign-in"
      }

      env {
        name  = "NEXT_PUBLIC_CLERK_SIGN_UP_URL"
        value = "/sign-up"
      }

      env {
        name  = "NEXT_PUBLIC_APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = var.app_insights_connection_string
      }

      # Startup probe - allow longer startup for Next.js cold starts
      startup_probe {
        transport              = "HTTP"
        path                   = "/"
        port                   = 3000
        initial_delay          = 5
        interval_seconds       = 10
        failure_count_threshold = 30 # Allow up to 5 minutes for Next.js cold start
        timeout                = 3
      }

      # Liveness probe
      liveness_probe {
        transport              = "HTTP"
        path                   = "/"
        port                   = 3000
        initial_delay          = 0
        interval_seconds       = 30
        failure_count_threshold = 3
        timeout                = 5
      }

      # Readiness probe
      readiness_probe {
        transport              = "HTTP"
        path                   = "/"
        port                   = 3000
        initial_delay          = 0
        interval_seconds       = 10
        failure_count_threshold = 3
        timeout                = 3
      }
    }
  }

  ingress {
    external_enabled           = true
    target_port                = 3000
    transport                  = "http"
    allow_insecure_connections = false

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  tags = merge(var.tags, {
    "azd-service-name" = "frontend"
  })

  lifecycle {
    ignore_changes = [
      # Ignore image changes as these are managed by azd deploy
      template[0].container[0].image,
    ]
  }

  depends_on = [azurerm_container_app.api]
}
