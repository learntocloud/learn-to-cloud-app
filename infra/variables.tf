# -----------------------------------------------------------------------------
# Required Variables
# -----------------------------------------------------------------------------
variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "clerk_publishable_key" {
  description = "Clerk publishable key"
  type        = string
}

variable "clerk_secret_key" {
  description = "Clerk secret key"
  type        = string
  sensitive   = true
}

variable "clerk_webhook_signing_secret" {
  description = "Clerk webhook signing secret"
  type        = string
  sensitive   = true
}

variable "google_api_key" {
  description = "Google API key for Gemini"
  type        = string
  sensitive   = true
}

variable "labs_verification_secret" {
  description = "CTF master secret for flag generation"
  type        = string
  sensitive   = true
}

# -----------------------------------------------------------------------------
# Optional Variables with Defaults
# -----------------------------------------------------------------------------
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

variable "frontend_custom_domain" {
  description = "Custom domain for the frontend (e.g., app.learntocloud.guide). Used for CORS."
  type        = string
  default     = ""
}

variable "alert_email" {
  description = "Email address to receive monitoring alerts"
  type        = string
  default     = "learntocloudguide@gmail.com"
}

variable "slack_webhook_url" {
  description = "Optional Slack webhook URL for warning alerts (Sev2). Leave empty to disable."
  type        = string
  default     = ""
  sensitive   = true
}
