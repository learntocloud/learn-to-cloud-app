# Registry Module Outputs

output "container_registry_id" {
  description = "ID of the Container Registry"
  value       = azurerm_container_registry.main.id
}

output "container_registry_name" {
  description = "Name of the Container Registry"
  value       = azurerm_container_registry.main.name
}

output "container_registry_login_server" {
  description = "Login server URL for the Container Registry"
  value       = azurerm_container_registry.main.login_server
}
