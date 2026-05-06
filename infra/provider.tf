terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.0"
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

provider "azapi" {}

resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false

  lifecycle {
    ignore_changes = all
  }
}

locals {
  api_postgres_role                             = coalesce(var.postgres_api_runtime_role, "ltc_api_runtime_${var.environment}")
  key_vault_name                                = "kv-ltc-${var.environment}-${local.suffix}"
  migration_postgres_role                       = coalesce(var.postgres_migration_role, "ltc-postgres-migrations-${var.environment}")
  verification_functions_postgres_role          = coalesce(var.postgres_verification_functions_role, "ltc_verification_functions_${var.environment}")
  verification_functions_storage_account_prefix = substr(replace("stltcfunc${lower(var.environment)}", "-", ""), 0, 18)
  verification_functions_storage_account_name   = "${local.verification_functions_storage_account_prefix}${local.suffix}"
  verification_functions_task_hub_name          = "verification-${var.environment}"
  suffix                                        = random_string.suffix.result
  resource_group_name                           = "rg-ltc-${var.environment}"
  tags = {
    environment = var.environment
    project     = "learntocloud"
    managed_by  = "terraform"
  }
}
