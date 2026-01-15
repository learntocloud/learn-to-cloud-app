# Provider Configuration

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }

    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }

  # Azure authentication is handled by:
  # 1. Azure CLI (az login) for local development
  # 2. Managed Identity or Service Principal in CI/CD
  # 3. Environment variables (ARM_SUBSCRIPTION_ID, ARM_TENANT_ID, etc.)
}

provider "random" {
  # Random provider configuration (no specific settings required)
}
