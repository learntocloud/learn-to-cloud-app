# Root Module Outputs
# These outputs are used by azd for deployment

# Resource Group
output "AZURE_RESOURCE_GROUP" {
  description = "Resource group name"
  value       = module.foundation.resource_group_name
}

output "AZURE_LOCATION" {
  description = "Azure region"
  value       = module.foundation.location
}

# Service Endpoints
output "apiUrl" {
  description = "API Container App URL"
  value       = module.container_apps.api_container_app_url
}

output "frontendUrl" {
  description = "Frontend Container App URL"
  value       = module.container_apps.frontend_container_app_url
}

output "postgresHost" {
  description = "PostgreSQL server FQDN"
  value       = module.database.postgres_fqdn
}

# Key Vault
output "keyVaultName" {
  description = "Key Vault name"
  value       = module.secrets.key_vault_name
}

output "keyVaultUri" {
  description = "Key Vault URI"
  value       = module.secrets.key_vault_uri
}

# Container Registry (for azd deploy)
output "AZURE_CONTAINER_REGISTRY_NAME" {
  description = "Container Registry name"
  value       = module.registry.container_registry_name
}

output "AZURE_CONTAINER_REGISTRY_ENDPOINT" {
  description = "Container Registry login server"
  value       = module.registry.container_registry_login_server
}
