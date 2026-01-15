# Identity Module: User-Assigned Managed Identity
# Shared by both Container Apps for Key Vault access

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

# User-Assigned Managed Identity
# This identity is granted Key Vault Secrets User role and is used by both Container Apps
resource "azurerm_user_assigned_identity" "container_app_identity" {
  name                = "id-${var.app_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags
}
