output "azure_portal_url" {
  description = "Link to the resource group in Azure Portal"
  value       = "https://portal.azure.com/#@/resource/subscriptions/${var.subscription_id}/resourceGroups/${azurerm_resource_group.main.name}/overview"
}

output "database_host" {
  description = "PostgreSQL server hostname"
  value       = azurerm_postgresql_flexible_server.main.fqdn
}

output "postgres_server_name" {
  description = "PostgreSQL server name"
  value       = azurerm_postgresql_flexible_server.main.name
}

output "postgres_database_name" {
  description = "PostgreSQL database name"
  value       = azurerm_postgresql_flexible_server_database.main.name
}

output "application_insights_connection_string" {
  description = "Application Insights connection string"
  value       = azurerm_application_insights.main.connection_string
  sensitive   = true
}

output "frontend_application_insights_connection_string" {
  description = "Frontend Application Insights connection string"
  value       = azurerm_application_insights.frontend.connection_string
  sensitive   = true
}

output "frontend_application_insights_name" {
  description = "Frontend Application Insights resource name"
  value       = azurerm_application_insights.frontend.name
}

output "action_group_id" {
  description = "Action group ID for critical alerts (Sev1)"
  value       = azurerm_monitor_action_group.critical.id
}

output "key_vault_name" {
  description = "Key Vault name for runtime app secrets"
  value       = azurerm_key_vault.main.name
}

output "key_vault_uri" {
  description = "Key Vault URI for runtime app secrets"
  value       = azurerm_key_vault.main.vault_uri
}

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

output "api_url" {
  description = "API URL (for CI/CD)"
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}

output "api_container_app_name" {
  description = "API Container App name (for CI/CD)"
  value       = azurerm_container_app.api.name
}

output "migration_job_name" {
  description = "Container Apps Job name used to run database migrations"
  value       = azurerm_container_app_job.migrations.name
}

output "migration_identity_client_id" {
  description = "Client ID for the migration job managed identity"
  value       = azurerm_user_assigned_identity.migrations.client_id
}

output "migration_identity_id" {
  description = "Resource ID for the migration job managed identity"
  value       = azurerm_user_assigned_identity.migrations.id
}

output "migration_identity_principal_id" {
  description = "Principal ID for mapping the migration job identity to PostgreSQL"
  value       = azurerm_user_assigned_identity.migrations.principal_id
}

output "migration_postgres_role" {
  description = "PostgreSQL role used by the Azure Container Apps migration job"
  value       = local.migration_postgres_role
}

output "verification_functions_name" {
  description = "Azure Functions app name used for Durable verification jobs"
  value       = azurerm_function_app_flex_consumption.verification.name
}

output "verification_functions_url" {
  description = "Azure Functions app URL used by the API Durable client"
  value       = "https://${azurerm_function_app_flex_consumption.verification.default_hostname}"
}

output "verification_functions_identity_client_id" {
  description = "Client ID for the verification Functions managed identity"
  value       = azurerm_user_assigned_identity.verification_functions.client_id
}

output "verification_functions_identity_id" {
  description = "Resource ID for the verification Functions managed identity"
  value       = azurerm_user_assigned_identity.verification_functions.id
}

output "verification_functions_identity_principal_id" {
  description = "Principal ID for mapping the verification Functions identity to PostgreSQL"
  value       = azurerm_user_assigned_identity.verification_functions.principal_id
}

output "verification_functions_postgres_role" {
  description = "PostgreSQL role used by the verification Functions app"
  value       = local.verification_functions_postgres_role
}

output "durable_task_scheduler_name" {
  description = "Durable Task Scheduler name used by verification Functions"
  value       = azapi_resource.verification_scheduler.name
}

output "durable_task_hub_name" {
  description = "Durable Task Scheduler task hub name used by verification Functions"
  value       = azapi_resource.verification_task_hub.name
}
