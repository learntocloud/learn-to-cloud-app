# Foundation Module Variables

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

variable "tags" {
  description = "Resource tags"
  type        = map(string)
}

variable "existing_unique_suffix" {
  description = "Existing unique suffix from Bicep deployment (for import). Leave empty for new deployments."
  type        = string
  default     = ""
}
