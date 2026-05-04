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

variable "github_client_id" {
  description = "GitHub OAuth App client ID"
  type        = string
}

variable "github_client_secret" {
  description = "GitHub OAuth App client secret"
  type        = string
  sensitive   = true
}

variable "github_token" {
  description = "Read-only GitHub API token used for server-side verification requests"
  type        = string
  sensitive   = true

  validation {
    condition     = length(trimspace(var.github_token)) > 0
    error_message = "github_token must be set to a read-only GitHub API token for production verification."
  }
}

variable "session_secret_key" {
  description = "Secret key for signing session cookies"
  type        = string
  sensitive   = true
}

variable "labs_verification_secret" {
  description = "CTF master secret for flag generation"
  type        = string
  sensitive   = true
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
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
