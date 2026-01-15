# Observability Module Outputs

output "log_analytics_workspace_id" {
  description = "ID of the Log Analytics workspace"
  value       = azurerm_log_analytics_workspace.main.id
}

output "log_analytics_workspace_customer_id" {
  description = "Customer ID (workspace ID) for Log Analytics"
  value       = azurerm_log_analytics_workspace.main.workspace_id
}

output "log_analytics_workspace_primary_shared_key" {
  description = "Primary shared key for Log Analytics"
  value       = azurerm_log_analytics_workspace.main.primary_shared_key
  sensitive   = true
}

output "app_insights_id" {
  description = "ID of Application Insights"
  value       = azurerm_application_insights.main.id
}

output "app_insights_instrumentation_key" {
  description = "Instrumentation key for Application Insights"
  value       = azurerm_application_insights.main.instrumentation_key
  sensitive   = true
}

output "app_insights_connection_string" {
  description = "Connection string for Application Insights"
  value       = azurerm_application_insights.main.connection_string
  sensitive   = true
}

output "app_insights_name" {
  description = "Name of Application Insights"
  value       = azurerm_application_insights.main.name
}
