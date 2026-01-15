# Foundation Module Outputs

output "resource_group_name" {
  description = "Name of the resource group"
  value       = azurerm_resource_group.main.name
}

output "resource_group_id" {
  description = "ID of the resource group"
  value       = azurerm_resource_group.main.id
}

output "location" {
  description = "Azure region"
  value       = azurerm_resource_group.main.location
}

output "unique_suffix" {
  description = "Unique suffix for resource naming"
  value       = random_string.unique_suffix.result
}

output "tags" {
  description = "Resource tags"
  value       = var.tags
}
