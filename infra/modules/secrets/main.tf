# Secrets Module: Key Vault, Secrets, and RBAC

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.9"
    }
  }
}

# Data source for current subscription (needed for tenant ID)
data "azurerm_client_config" "current" {}

# Key Vault for secure secret management
# Key Vault names must be 3-24 characters, alphanumeric and hyphens only
resource "azurerm_key_vault" "main" {
  name                = "kv-ltc-${var.environment}-${var.unique_suffix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  tenant_id           = data.azurerm_client_config.current.tenant_id

  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = 90
  purge_protection_enabled   = false # Set to true in production if needed

  network_acls {
    bypass         = "AzureServices"
    default_action = "Allow" # Consider 'Deny' with private endpoints for production
  }

  tags = var.tags
}

# Key Vault Secrets
resource "azurerm_key_vault_secret" "clerk_secret_key" {
  name         = "clerk-secret-key"
  value        = var.clerk_secret_key
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.container_app_identity_kv_secrets_user]
}

resource "azurerm_key_vault_secret" "clerk_webhook_signing_secret" {
  name         = "clerk-webhook-signing-secret"
  value        = var.clerk_webhook_signing_secret
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.container_app_identity_kv_secrets_user]
}

resource "azurerm_key_vault_secret" "postgres_admin_password" {
  name         = "postgres-admin-password"
  value        = var.postgres_admin_password
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.container_app_identity_kv_secrets_user]
}

# Google API key secret (conditional)
resource "azurerm_key_vault_secret" "google_api_key" {
  count        = var.google_api_key != "" ? 1 : 0
  name         = "google-api-key"
  value        = var.google_api_key
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.container_app_identity_kv_secrets_user]
}

# RBAC: Grant Key Vault Secrets User role to User-Assigned Managed Identity
# This allows Container Apps to read secrets from Key Vault
resource "azurerm_role_assignment" "container_app_identity_kv_secrets_user" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = var.container_app_identity_principal_id
  principal_type       = "ServicePrincipal"
}

# Wait for RBAC to propagate before Container Apps can use the identity
# Azure RBAC can take up to 10 minutes to propagate
resource "time_sleep" "wait_for_rbac_propagation" {
  depends_on = [azurerm_role_assignment.container_app_identity_kv_secrets_user]

  triggers = {
    key_vault_id  = azurerm_key_vault.main.id
    principal_id  = var.container_app_identity_principal_id
    role_name     = "Key Vault Secrets User"
    assignment_id = azurerm_role_assignment.container_app_identity_kv_secrets_user.id
  }

  create_duration = "300s"
}
