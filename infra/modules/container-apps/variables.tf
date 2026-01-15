# Container Apps Module Variables

variable "app_name" {
  description = "Application name (learntocloud)"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "location" {
  description = "Azure region for resources"
  type        = string
}

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "log_analytics_workspace_id" {
  description = "ID of the Log Analytics workspace"
  type        = string
}

variable "user_assigned_identity_id" {
  description = "ID of the user-assigned managed identity"
  type        = string
}

variable "container_registry_login_server" {
  description = "Login server URL for the Container Registry"
  type        = string
}

variable "postgres_fqdn" {
  description = "Fully qualified domain name of the PostgreSQL server"
  type        = string
}

variable "clerk_publishable_key" {
  description = "Clerk publishable key for frontend authentication"
  type        = string
}

variable "clerk_secret_key_kv_id" {
  description = "Key Vault secret ID for Clerk secret key"
  type        = string
}

variable "clerk_webhook_signing_secret_kv_id" {
  description = "Key Vault secret ID for Clerk webhook signing secret"
  type        = string
}

variable "redis_connection_string_kv_id" {
  description = "Key Vault secret ID for Redis connection string (if enabled)"
  type        = string
  default     = null
}

variable "google_api_key_kv_id" {
  description = "Key Vault secret ID for Google API key (if provided)"
  type        = string
  default     = null
}

variable "app_insights_connection_string" {
  description = "Application Insights connection string"
  type        = string
  sensitive   = true
}

variable "frontend_custom_domain" {
  description = "Custom domain for the frontend app (optional)"
  type        = string
  default     = ""
}

variable "frontend_managed_certificate_name" {
  description = "Name of the existing managed certificate resource (required when binding a custom domain)"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
}
