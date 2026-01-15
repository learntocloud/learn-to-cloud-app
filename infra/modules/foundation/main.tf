# Foundation Module: Resource Group and Naming Convention
# This module creates the base resource group and handles unique suffix generation

terraform {
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

# Unique suffix for resource naming
# This will be imported with the existing value from Bicep deployment
resource "random_string" "unique_suffix" {
  length  = 13
  special = false
  upper   = false

  # Ignore changes after import to preserve existing value
  lifecycle {
    ignore_changes = [length, special, upper]
  }
}

# Resource Group
resource "azurerm_resource_group" "main" {
  name     = "rg-${var.app_name}-${var.environment}"
  location = var.location
  tags     = var.tags
}
