# Container Apps Module Outputs

output "container_app_environment_id" {
  description = "ID of the Container Apps Environment"
  value       = azurerm_container_app_environment.main.id
}

output "container_app_environment_default_domain" {
  description = "Default domain of the Container Apps Environment"
  value       = azurerm_container_app_environment.main.default_domain
}

output "api_container_app_id" {
  description = "ID of the API Container App"
  value       = azurerm_container_app.api.id
}

output "api_container_app_name" {
  description = "Name of the API Container App"
  value       = azurerm_container_app.api.name
}

output "api_container_app_fqdn" {
  description = "FQDN of the API Container App"
  value       = azurerm_container_app.api.ingress[0].fqdn
}

output "api_container_app_url" {
  description = "URL of the API Container App"
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}

output "api_container_app_principal_id" {
  description = "Principal ID of the API Container App (system-assigned identity)"
  value       = azurerm_container_app.api.identity[0].principal_id
}

output "frontend_container_app_id" {
  description = "ID of the Frontend Container App"
  value       = azurerm_container_app.frontend.id
}

output "frontend_container_app_name" {
  description = "Name of the Frontend Container App"
  value       = azurerm_container_app.frontend.name
}

output "frontend_container_app_fqdn" {
  description = "FQDN of the Frontend Container App"
  value       = azurerm_container_app.frontend.ingress[0].fqdn
}

output "frontend_container_app_url" {
  description = "URL of the Frontend Container App"
  value       = "https://${azurerm_container_app.frontend.ingress[0].fqdn}"
}

output "frontend_container_app_principal_id" {
  description = "Principal ID of the Frontend Container App (system-assigned identity)"
  value       = azurerm_container_app.frontend.identity[0].principal_id
}
