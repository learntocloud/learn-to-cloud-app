variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
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
