# Monitoring Module Variables

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

variable "api_container_app_id" {
  description = "ID of the API Container App"
  type        = string
}

variable "api_container_app_name" {
  description = "Name of the API Container App"
  type        = string
}

variable "frontend_container_app_id" {
  description = "ID of the Frontend Container App"
  type        = string
}

variable "frontend_container_app_name" {
  description = "Name of the Frontend Container App"
  type        = string
}

variable "postgres_server_id" {
  description = "ID of the PostgreSQL server"
  type        = string
}

variable "app_insights_id" {
  description = "ID of Application Insights"
  type        = string
}

variable "alert_email_address" {
  description = "Email address for alert notifications (optional)"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
}
