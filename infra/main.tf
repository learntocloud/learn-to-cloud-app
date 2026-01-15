# Learn to Cloud - Terraform Root Module
# Orchestrates all infrastructure modules

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
}

# Local variables
locals {
  app_name = "learntocloud"

  tags = {
    environment = var.environment
    project     = "learn-to-cloud"
    managed_by  = "terraform"
  }
}

# Foundation Module: Resource Group and Naming
module "foundation" {
  source = "./modules/foundation"

  app_name               = local.app_name
  environment            = var.environment
  location               = var.location
  tags                   = local.tags
  existing_unique_suffix = var.existing_unique_suffix
}

# Identity Module: User-Assigned Managed Identity
module "identity" {
  source = "./modules/identity"

  app_name            = local.app_name
  environment         = var.environment
  location            = var.location
  resource_group_name = module.foundation.resource_group_name
  tags                = local.tags
}

# Observability Module: Log Analytics and Application Insights
module "observability" {
  source = "./modules/observability"

  app_name            = local.app_name
  environment         = var.environment
  location            = var.location
  resource_group_name = module.foundation.resource_group_name
  tags                = local.tags
}

# Database Module: PostgreSQL Flexible Server
module "database" {
  source = "./modules/database"

  app_name                = local.app_name
  environment             = var.environment
  location                = var.location
  resource_group_name     = module.foundation.resource_group_name
  unique_suffix           = module.foundation.unique_suffix
  postgres_admin_password = var.postgres_admin_password
  tags                    = local.tags
}

# Cache Module: Azure Cache for Redis (conditional)
module "cache" {
  source = "./modules/cache"

  app_name            = local.app_name
  environment         = var.environment
  location            = var.location
  resource_group_name = module.foundation.resource_group_name
  unique_suffix       = module.foundation.unique_suffix
  enable_redis        = var.enable_redis
  tags                = local.tags
}

# Secrets Module: Key Vault, Secrets, and RBAC
module "secrets" {
  source = "./modules/secrets"

  app_name                            = local.app_name
  environment                         = var.environment
  location                            = var.location
  resource_group_name                 = module.foundation.resource_group_name
  unique_suffix                       = module.foundation.unique_suffix
  container_app_identity_principal_id = module.identity.identity_principal_id
  clerk_secret_key                    = var.clerk_secret_key
  clerk_webhook_signing_secret        = var.clerk_webhook_signing_secret
  postgres_admin_password             = var.postgres_admin_password
  enable_redis                        = var.enable_redis
  redis_connection_string             = module.cache.redis_connection_string
  google_api_key                      = var.google_api_key
  tags                                = local.tags
}

# Container Apps Module: Environment, API, and Frontend
module "container_apps" {
  source = "./modules/container-apps"

  app_name                            = local.app_name
  environment                         = var.environment
  location                            = var.location
  resource_group_name                 = module.foundation.resource_group_name
  log_analytics_workspace_id          = module.observability.log_analytics_workspace_id
  user_assigned_identity_id           = module.identity.identity_id
  container_registry_login_server     = module.registry.container_registry_login_server
  postgres_fqdn                       = module.database.postgres_fqdn
  clerk_publishable_key               = var.clerk_publishable_key
  clerk_secret_key_kv_id              = module.secrets.clerk_secret_key_id
  clerk_webhook_signing_secret_kv_id  = module.secrets.clerk_webhook_signing_secret_id
  redis_connection_string_kv_id       = module.secrets.redis_connection_string_id
  google_api_key_kv_id                = module.secrets.google_api_key_id
  app_insights_connection_string      = module.observability.app_insights_connection_string
  frontend_custom_domain              = var.frontend_custom_domain
  frontend_managed_certificate_name   = var.frontend_managed_certificate_name
  tags                                = local.tags

  depends_on = [module.secrets]
}

# Registry Module: Container Registry
module "registry" {
  source = "./modules/registry"

  app_name            = local.app_name
  environment         = var.environment
  location            = var.location
  resource_group_name = module.foundation.resource_group_name
  unique_suffix       = module.foundation.unique_suffix
  tags                = local.tags
}

# Monitoring Module: Action Groups and Metric Alerts
module "monitoring" {
  source = "./modules/monitoring"

  app_name                    = local.app_name
  environment                 = var.environment
  location                    = var.location
  resource_group_name         = module.foundation.resource_group_name
  api_container_app_id        = module.container_apps.api_container_app_id
  api_container_app_name      = module.container_apps.api_container_app_name
  frontend_container_app_id   = module.container_apps.frontend_container_app_id
  frontend_container_app_name = module.container_apps.frontend_container_app_name
  postgres_server_id          = module.database.postgres_server_id
  app_insights_id             = module.observability.app_insights_id
  alert_email_address         = var.alert_email_address
  tags                        = local.tags
}

# ACR Pull Role Assignments
# These are at root level to avoid circular dependency between registry and container_apps modules
resource "azurerm_role_assignment" "api_acr_pull" {
  scope                = module.registry.container_registry_id
  role_definition_name = "AcrPull"
  principal_id         = module.container_apps.api_container_app_principal_id
  principal_type       = "ServicePrincipal"

  depends_on = [
    module.registry,
    module.container_apps
  ]
}

resource "azurerm_role_assignment" "frontend_acr_pull" {
  scope                = module.registry.container_registry_id
  role_definition_name = "AcrPull"
  principal_id         = module.container_apps.frontend_container_app_principal_id
  principal_type       = "ServicePrincipal"

  depends_on = [
    module.registry,
    module.container_apps
  ]
}
