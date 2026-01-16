# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------
output "resource_group_name" {
  description = "Name of the resource group"
  value       = azurerm_resource_group.main.name
}

output "api_url" {
  description = "URL of the API container app"
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}

output "frontend_url" {
  description = "URL of the frontend container app"
  value       = "https://${azurerm_container_app.frontend.ingress[0].fqdn}"
}

output "container_registry" {
  description = "Container registry login server"
  value       = azurerm_container_registry.main.login_server
}

output "database_host" {
  description = "PostgreSQL server hostname"
  value       = azurerm_postgresql_flexible_server.main.fqdn
}

output "application_insights_connection_string" {
  description = "Application Insights connection string"
  value       = azurerm_application_insights.main.connection_string
  sensitive   = true
}

output "azure_portal_url" {
  description = "Link to the resource group in Azure Portal"
  value       = "https://portal.azure.com/#@/resource/subscriptions/${var.subscription_id}/resourceGroups/${azurerm_resource_group.main.name}/overview"
}

# Outputs for CI/CD workflow
output "AZURE_RESOURCE_GROUP" {
  description = "Resource group name (for CI/CD)"
  value       = azurerm_resource_group.main.name
}

output "AZURE_CONTAINER_REGISTRY_NAME" {
  description = "Container registry name (for CI/CD)"
  value       = azurerm_container_registry.main.name
}

output "AZURE_CONTAINER_REGISTRY_ENDPOINT" {
  description = "Container registry endpoint (for CI/CD)"
  value       = azurerm_container_registry.main.login_server
}

output "apiUrl" {
  description = "API URL (for CI/CD)"
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}

output "api_identity_principal_id" {
  description = "API managed identity principal ID (for Entra admin setup)"
  value       = azurerm_user_assigned_identity.api.principal_id
}

output "postgres_server_name" {
  description = "PostgreSQL server name"
  value       = azurerm_postgresql_flexible_server.main.name
}
