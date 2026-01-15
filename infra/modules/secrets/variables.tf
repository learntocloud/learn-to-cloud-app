# Secrets Module Variables

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

variable "unique_suffix" {
  description = "Unique suffix for resource naming"
  type        = string
}

variable "container_app_identity_principal_id" {
  description = "Principal ID of the user-assigned managed identity"
  type        = string
}

variable "clerk_secret_key" {
  description = "Clerk secret key for backend authentication"
  type        = string
  sensitive   = true
}

variable "clerk_webhook_signing_secret" {
  description = "Clerk webhook signing secret for verifying webhook payloads"
  type        = string
  sensitive   = true
}

variable "postgres_admin_password" {
  description = "PostgreSQL administrator password"
  type        = string
  sensitive   = true
}

variable "enable_redis" {
  description = "Whether Redis is enabled"
  type        = bool
  default     = false
}

variable "redis_connection_string" {
  description = "Redis connection string (if Redis is enabled)"
  type        = string
  sensitive   = true
  default     = null
}

variable "google_api_key" {
  description = "Google API key for AI features"
  type        = string
  sensitive   = true
  default     = ""
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
}
