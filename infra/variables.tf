variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "postgres_entra_admin_object_id" {
  description = "Object ID of the Microsoft Entra principal that administers PostgreSQL. Use a DBA/break-glass group, not the API runtime identity."
  type        = string

  validation {
    condition     = length(trimspace(var.postgres_entra_admin_object_id)) > 0
    error_message = "postgres_entra_admin_object_id must be set to the object ID of a dedicated PostgreSQL Entra admin principal."
  }
}

variable "postgres_entra_admin_principal_name" {
  description = "Display name of the Microsoft Entra principal that administers PostgreSQL."
  type        = string

  validation {
    condition     = length(trimspace(var.postgres_entra_admin_principal_name)) > 0
    error_message = "postgres_entra_admin_principal_name must be set to the PostgreSQL Entra admin principal display name."
  }
}

variable "postgres_entra_admin_principal_type" {
  description = "Type of the Microsoft Entra principal that administers PostgreSQL."
  type        = string
  default     = "Group"

  validation {
    condition     = contains(["User", "Group", "ServicePrincipal"], var.postgres_entra_admin_principal_type)
    error_message = "postgres_entra_admin_principal_type must be User, Group, or ServicePrincipal."
  }
}

variable "postgres_api_runtime_role" {
  description = "PostgreSQL role used by the API at runtime. It is mapped to the API managed identity but is not the Azure identity name."
  type        = string
  default     = null

  validation {
    condition     = var.postgres_api_runtime_role == null || can(regex("^[A-Za-z_][A-Za-z0-9_]*$", var.postgres_api_runtime_role))
    error_message = "postgres_api_runtime_role must be a valid PostgreSQL role identifier using letters, numbers, and underscores, and must not start with a number."
  }
}

variable "postgres_migration_role" {
  description = "PostgreSQL role used by the Azure Container Apps migration job. Defaults to ltc-postgres-migrations-<environment>."
  type        = string
  default     = null

  validation {
    condition     = var.postgres_migration_role == null ? true : length(trimspace(var.postgres_migration_role)) > 0 && length(var.postgres_migration_role) <= 63
    error_message = "postgres_migration_role must be a non-empty PostgreSQL role name no longer than 63 characters when set."
  }
}

variable "postgres_verification_functions_role" {
  description = "PostgreSQL role used by the verification Azure Functions app. Defaults to ltc_verification_functions_<environment>."
  type        = string
  default     = null

  validation {
    condition     = var.postgres_verification_functions_role == null || can(regex("^[A-Za-z_][A-Za-z0-9_]*$", var.postgres_verification_functions_role))
    error_message = "postgres_verification_functions_role must be a valid PostgreSQL role identifier using letters, numbers, and underscores, and must not start with a number."
  }
}

variable "durable_task_scheduler_ip_allowlist" {
  description = "CIDR ranges allowed to connect to the Durable Task Scheduler endpoint."
  type        = list(string)
  default     = ["0.0.0.0/0"]

  validation {
    condition     = length(var.durable_task_scheduler_ip_allowlist) > 0
    error_message = "durable_task_scheduler_ip_allowlist must include at least one IPv4, IPv6, or CIDR range."
  }
}

variable "durable_task_dashboard_reader_group_object_ids_by_environment" {
  description = "Microsoft Entra group object IDs allowed to view Durable Task Scheduler dashboard orchestration data, keyed by environment."
  type        = map(list(string))
  default = {
    dev = ["2141d117-ca04-40c9-a8e2-a0af566791a3"]
  }

  validation {
    condition = alltrue([
      for object_id in flatten(values(var.durable_task_dashboard_reader_group_object_ids_by_environment)) :
      can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", object_id))
    ])
    error_message = "durable_task_dashboard_reader_group_object_ids_by_environment values must be valid Microsoft Entra object IDs."
  }
}

variable "foundry_model_deployment_name" {
  description = "Foundry model deployment name used by the verification LLM grader."
  type        = string
  default     = "gpt-5-mini-verifier"

  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9_.-]{1,63}$", var.foundry_model_deployment_name))
    error_message = "foundry_model_deployment_name must be 2-64 characters and contain only letters, numbers, underscores, periods, or hyphens."
  }
}

variable "foundry_model_name" {
  description = "Foundry model name deployed for verification LLM grading."
  type        = string
  default     = "gpt-5-mini"

  validation {
    condition     = length(trimspace(var.foundry_model_name)) > 0
    error_message = "foundry_model_name must be set."
  }
}

variable "foundry_model_version" {
  description = "Pinned Foundry model version deployed for verification LLM grading."
  type        = string
  default     = "2025-08-07"

  validation {
    condition     = length(trimspace(var.foundry_model_version)) > 0
    error_message = "foundry_model_version must be set to a pinned model version."
  }
}

variable "foundry_model_sku_name" {
  description = "Foundry model deployment SKU name."
  type        = string
  default     = "GlobalStandard"

  validation {
    condition     = length(trimspace(var.foundry_model_sku_name)) > 0
    error_message = "foundry_model_sku_name must be set."
  }
}

variable "foundry_model_capacity" {
  description = "Foundry model deployment capacity. For Azure OpenAI Standard/GlobalStandard, this is in thousands of tokens per minute."
  type        = number
  default     = 1

  validation {
    condition     = var.foundry_model_capacity > 0
    error_message = "foundry_model_capacity must be greater than zero."
  }
}

variable "foundry_location" {
  description = "Azure region for the verification Foundry account and project. Defaults to a GlobalStandard GPT-5 mini region."
  type        = string
  default     = "eastus2"

  validation {
    condition     = length(trimspace(var.foundry_location)) > 0
    error_message = "foundry_location must be set."
  }
}

variable "github_client_id" {
  description = "GitHub OAuth App client ID"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod."
  }
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "centralus"
}

variable "alert_emails" {
  description = "Email addresses to receive monitoring alerts"
  type        = list(string)
  default     = ["learntocloudguide@gmail.com"]
}

variable "api_min_replicas" {
  description = "Minimum API Container App replicas. Defaults to 0 so the API can scale to zero."
  type        = number
  default     = null

  validation {
    condition     = var.api_min_replicas == null ? true : var.api_min_replicas >= 0
    error_message = "api_min_replicas must be zero or greater."
  }
}

variable "api_max_replicas" {
  description = "Maximum API Container App replicas."
  type        = number
  default     = null

  validation {
    condition     = var.api_max_replicas == null ? true : var.api_max_replicas >= 1
    error_message = "api_max_replicas must be at least 1."
  }
}

variable "postgres_sku_name" {
  description = "PostgreSQL Flexible Server SKU. Defaults to the cheapest configured burstable SKU."
  type        = string
  default     = null

  validation {
    condition     = var.postgres_sku_name == null ? true : length(trimspace(var.postgres_sku_name)) > 0
    error_message = "postgres_sku_name must be non-empty when set."
  }
}

variable "postgres_storage_mb" {
  description = "PostgreSQL Flexible Server storage size in MB."
  type        = number
  default     = null

  validation {
    condition     = var.postgres_storage_mb == null ? true : var.postgres_storage_mb >= 32768
    error_message = "postgres_storage_mb must be at least 32768 MB when set."
  }
}

variable "postgres_backup_retention_days" {
  description = "PostgreSQL Flexible Server backup retention in days."
  type        = number
  default     = null

  validation {
    condition     = var.postgres_backup_retention_days == null ? true : var.postgres_backup_retention_days >= 7 && var.postgres_backup_retention_days <= 35
    error_message = "postgres_backup_retention_days must be between 7 and 35 when set."
  }
}

variable "postgres_geo_redundant_backup_enabled" {
  description = "Whether PostgreSQL geo-redundant backup is enabled. Decide before initial production creation."
  type        = bool
  default     = null
}

variable "postgres_zone" {
  description = "PostgreSQL Flexible Server availability zone. Set to null only when the target region/SKU supports zone omission."
  type        = string
  default     = null

  validation {
    condition     = var.postgres_zone == null ? true : can(regex("^[1-9][0-9]*$", var.postgres_zone))
    error_message = "postgres_zone must be a positive zone number string when set."
  }
}
