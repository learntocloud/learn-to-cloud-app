# -----------------------------------------------------------------------------
# Required Variables
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# LLM — Azure OpenAI model deployment for code analysis
# Terraform deploys the Azure OpenAI resource and model automatically.
# The endpoint and API key are wired from the Terraform resource.
# -----------------------------------------------------------------------------
variable "llm_model" {
  description = "Azure OpenAI model to deploy (e.g. gpt-4o-mini, gpt-5-mini)"
  type        = string
  default     = "gpt-4o-mini"
}

variable "llm_model_version" {
  description = "Model version to deploy"
  type        = string
  default     = "2024-07-18"
}

variable "llm_capacity" {
  description = "Tokens-per-minute capacity in thousands (e.g. 10 = 10K TPM)"
  type        = number
  default     = 10
}

variable "llm_provider_type" {
  description = "Provider type for the SDK: azure, openai, or anthropic"
  type        = string
  default     = "azure"
}

variable "llm_wire_api" {
  description = "API format: completions or responses"
  type        = string
  default     = "completions"
}
