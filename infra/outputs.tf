# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# General
# -----------------------------------------------------------------------------
output "resource_group_name" {
  description = "Name of the resource group"
  value       = azurerm_resource_group.main.name
}

output "azure_portal_url" {
  description = "Link to the resource group in Azure Portal"
  value       = "https://portal.azure.com/#@/resource/subscriptions/${var.subscription_id}/resourceGroups/${azurerm_resource_group.main.name}/overview"
}

# -----------------------------------------------------------------------------
# API
# -----------------------------------------------------------------------------
output "api_url" {
  description = "URL of the API container app"
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}

output "api_identity_principal_id" {
  description = "API managed identity principal ID (for Entra admin setup)"
  value       = azurerm_user_assigned_identity.api.principal_id
}

# -----------------------------------------------------------------------------
# Container Registry
# -----------------------------------------------------------------------------
output "container_registry" {
  description = "Container registry login server"
  value       = azurerm_container_registry.main.login_server
}

# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------
output "database_host" {
  description = "PostgreSQL server hostname"
  value       = azurerm_postgresql_flexible_server.main.fqdn
}

output "postgres_server_name" {
  description = "PostgreSQL server name"
  value       = azurerm_postgresql_flexible_server.main.name
}

# -----------------------------------------------------------------------------
# Monitoring
# -----------------------------------------------------------------------------
output "application_insights_connection_string" {
  description = "Application Insights connection string"
  value       = azurerm_application_insights.main.connection_string
  sensitive   = true
}

output "dashboard_url" {
  description = "URL to the monitoring dashboard in Azure Portal"
  value       = "https://portal.azure.com/#@/dashboard/arm${azurerm_portal_dashboard.main.id}"
}

output "action_group_id" {
  description = "Action group ID for critical alerts (Sev1)"
  value       = azurerm_monitor_action_group.critical.id
}

output "warning_action_group_id" {
  description = "Action group ID for warning alerts (Sev2)"
  value       = azurerm_monitor_action_group.warning.id
}

# -----------------------------------------------------------------------------
# CI/CD Outputs
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# Azure OpenAI
# -----------------------------------------------------------------------------
output "openai_endpoint" {
  description = "Azure OpenAI endpoint used by the LLM CLI sidecar"
  value       = azurerm_cognitive_account.openai.endpoint
}

output "openai_model" {
  description = "Deployed model name"
  value       = azurerm_cognitive_deployment.llm.name
}
