terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  backend "azurerm" {
    resource_group_name  = "rg-terraform-state"
    storage_account_name = "stterraformstateb1ac9ddc"
    container_name       = "tfstate"
    key                  = "learn-to-cloud-dev.tfstate"
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = true
    }
  }
  subscription_id = var.subscription_id
}

# -----------------------------------------------------------------------------
# Random suffix for unique names
# -----------------------------------------------------------------------------
resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

locals {
  suffix              = random_string.suffix.result
  resource_group_name = "rg-ltc-${var.environment}"
  tags = {
    environment = var.environment
    project     = "learntocloud"
    managed_by  = "terraform"
  }
}

# -----------------------------------------------------------------------------
# Resource Group
# -----------------------------------------------------------------------------
resource "azurerm_resource_group" "main" {
  name     = local.resource_group_name
  location = var.location
  tags     = local.tags
}

# -----------------------------------------------------------------------------
# Log Analytics & Application Insights
# -----------------------------------------------------------------------------
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-ltc-${var.environment}-${local.suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_application_insights" "main" {
  name                = "appi-ltc-${var.environment}-${local.suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
  tags                = local.tags
}

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
# PostgreSQL Flexible Server
# -----------------------------------------------------------------------------
resource "azurerm_postgresql_flexible_server" "main" {
  name                          = "psql-ltc-${var.environment}-${local.suffix}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  version                       = "16"
  storage_mb                    = 32768
  sku_name                      = "B_Standard_B1ms"
  backup_retention_days         = 7
  geo_redundant_backup_enabled  = false
  public_network_access_enabled = true
  zone                          = "3"
  tags                          = local.tags

  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false
  }
}

resource "azurerm_postgresql_flexible_server_database" "main" {
  name      = "learntocloud"
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "allow_azure" {
  name             = "AllowAzureServices"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# -----------------------------------------------------------------------------
# Managed Identity for API
# -----------------------------------------------------------------------------
resource "azurerm_user_assigned_identity" "api" {
  name                = "id-ltc-api-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.tags
}

# -----------------------------------------------------------------------------
# PostgreSQL Entra Admin (Managed Identity)
# -----------------------------------------------------------------------------
data "azurerm_client_config" "current" {}

resource "azurerm_postgresql_flexible_server_active_directory_administrator" "api" {
  server_name         = azurerm_postgresql_flexible_server.main.name
  resource_group_name = azurerm_resource_group.main.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  object_id           = azurerm_user_assigned_identity.api.principal_id
  principal_name      = azurerm_user_assigned_identity.api.name
  principal_type      = "ServicePrincipal"
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
    min_replicas = 0
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
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.main.connection_string
      }

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }

      env {
        name  = "FRONTEND_URL"
        value = "https://ca-ltc-frontend-${var.environment}.${azurerm_container_app_environment.main.default_domain}"
      }

      liveness_probe {
        transport = "HTTP"
        path      = "/health"
        port      = 8000
        initial_delay            = 30
        interval_seconds         = 30
        timeout                  = 5
        failure_count_threshold  = 3
      }

      readiness_probe {
        transport = "HTTP"
        path      = "/health"
        port      = 8000
        interval_seconds         = 10
        timeout                  = 5
        failure_count_threshold  = 3
      }

      startup_probe {
        transport = "HTTP"
        path      = "/health"
        port      = 8000
        interval_seconds         = 10
        timeout                  = 5
        failure_count_threshold  = 30
      }
    }
  }

  depends_on = [azurerm_postgresql_flexible_server_database.main]
}

# -----------------------------------------------------------------------------
# Frontend Container App
# -----------------------------------------------------------------------------
resource "azurerm_container_app" "frontend" {
  name                         = "ca-ltc-frontend-${var.environment}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.tags

  registry {
    server               = azurerm_container_registry.main.login_server
    username             = azurerm_container_registry.main.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.main.admin_password
  }

  ingress {
    external_enabled = true
    target_port      = 80
    transport        = "http"

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = 0
    max_replicas = 3

    container {
      name   = "frontend"
      image  = "${azurerm_container_registry.main.login_server}/frontend:v6"
      cpu    = 0.25
      memory = "0.5Gi"

      liveness_probe {
        transport = "HTTP"
        path      = "/"
        port      = 80
        initial_delay            = 10
        interval_seconds         = 30
        timeout                  = 5
        failure_count_threshold  = 3
      }
    }
  }
}

# -----------------------------------------------------------------------------
# Custom Domain for Frontend (app.learntocloud.guide)
# -----------------------------------------------------------------------------
# Steps to add custom domain:
# 1. Add CNAME record: app.learntocloud.guide → ca-ltc-frontend-dev.<env-domain>
# 2. Add TXT record for verification: asuid.app → <custom-domain-verification-id>
# 3. Run: az containerapp hostname add --name ca-ltc-frontend-dev -g rg-ltc-dev --hostname app.learntocloud.guide
# 4. Run: az containerapp hostname bind --name ca-ltc-frontend-dev -g rg-ltc-dev --hostname app.learntocloud.guide --environment cae-ltc-dev --validation-method CNAME

output "custom_domain_verification_id" {
  description = "TXT record value for custom domain verification (asuid.app)"
  value       = azurerm_container_app_environment.main.custom_domain_verification_id
}
