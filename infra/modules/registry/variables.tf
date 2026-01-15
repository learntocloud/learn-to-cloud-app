# Registry Module Variables

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

variable "tags" {
  description = "Resource tags"
  type        = map(string)
}
