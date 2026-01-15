# Terraform Backend Configuration
# Stores state in Azure Storage for team collaboration and state locking

terraform {
  backend "azurerm" {
    # Backend configuration is provided via:
    # 1. Backend config file: terraform init -backend-config=backend.hcl
    # 2. Command-line flags: terraform init -backend-config="storage_account_name=..."
    # 3. Environment variables: ARM_ACCESS_KEY for authentication

    # Required values (provide via backend config or CLI):
    # resource_group_name  = "rg-terraform-state"
    # storage_account_name = "stterraformstateXXXX"
    # container_name       = "tfstate"
    # key                  = "learn-to-cloud-dev.tfstate" # Use ${environment}.tfstate for multiple environments

    resource_group_name  = "rg-terraform-state"
    storage_account_name = "stterraformstateb1ac9ddc"
    container_name       = "tfstate"
    key                  = "learn-to-cloud-dev.tfstate"

  }
}

# To initialize backend:
# 1. Run scripts/setup-backend.sh to create storage account
# 2. Set ARM_ACCESS_KEY environment variable
# 3. Run: terraform init
#
# For multiple environments, use different key values:
# terraform init -backend-config="key=learn-to-cloud-${var.environment}.tfstate"
