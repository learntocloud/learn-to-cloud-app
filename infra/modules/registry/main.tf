# Registry Module: Azure Container Registry and ACR Pull RBAC

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

# Azure Container Registry
resource "azurerm_container_registry" "main" {
  name                = "crltc${var.unique_suffix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "Basic"
  admin_enabled       = false # Use managed identities instead

  tags = var.tags
}

# Note: ACR Pull role assignments moved to root main.tf to avoid circular dependency
