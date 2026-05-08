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
  api_max_replicas                              = coalesce(var.api_max_replicas, 2)
  api_min_replicas                              = coalesce(var.api_min_replicas, 0)
  foundry_account_name                          = "ais-ltc-${var.environment}-${local.suffix}"
  foundry_project_endpoint                      = "https://${local.foundry_account_name}.services.ai.azure.com/api/projects/${local.foundry_project_name}"
  foundry_project_name                          = "ltc-verification-${var.environment}"
  api_postgres_role                             = coalesce(var.postgres_api_runtime_role, "ltc_api_runtime_${var.environment}")
  key_vault_name                                = "kv-ltc-${var.environment}-${local.suffix}"
  migration_postgres_role                       = coalesce(var.postgres_migration_role, "ltc-postgres-migrations-${var.environment}")
  postgres_backup_retention_days                = coalesce(var.postgres_backup_retention_days, 7)
  postgres_geo_redundant_backup_enabled         = coalesce(var.postgres_geo_redundant_backup_enabled, false)
  postgres_sku_name                             = coalesce(var.postgres_sku_name, "B_Standard_B1ms")
  postgres_storage_mb                           = coalesce(var.postgres_storage_mb, 32768)
  postgres_zone                                 = coalesce(var.postgres_zone, "3")
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
