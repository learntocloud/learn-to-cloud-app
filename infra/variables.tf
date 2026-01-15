# Root Module Variables

# Environment Configuration
variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "location" {
  description = "Azure region for resources"
  type        = string
}

# Unique Suffix (for imports)
variable "existing_unique_suffix" {
  description = "Existing unique suffix from Bicep deployment (for import). Leave empty for new deployments."
  type        = string
  default     = ""
}

# Database Configuration
variable "postgres_admin_password" {
  description = "PostgreSQL administrator password"
  type        = string
  sensitive   = true
}

# Clerk Authentication
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

variable "clerk_publishable_key" {
  description = "Clerk publishable key for frontend authentication"
  type        = string
}

# Optional Features
variable "enable_redis" {
  description = "Enable Azure Cache for Redis for distributed rate limiting"
  type        = bool
  default     = true
}

# Google API Key (Optional)
variable "google_api_key" {
  description = "Google API key for AI features (optional)"
  type        = string
  sensitive   = true
  default     = ""
}

# Custom Domain (Optional)
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

# Monitoring
variable "alert_email_address" {
  description = "Email address for alert notifications (optional)"
  type        = string
  default     = ""
}
