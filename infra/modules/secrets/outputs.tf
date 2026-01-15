# Secrets Module Outputs

output "key_vault_id" {
  description = "ID of the Key Vault"
  value       = azurerm_key_vault.main.id
}

output "key_vault_name" {
  description = "Name of the Key Vault"
  value       = azurerm_key_vault.main.name
}

output "key_vault_uri" {
  description = "URI of the Key Vault"
  value       = azurerm_key_vault.main.vault_uri
}

# Secret IDs for Container Apps to reference
output "clerk_secret_key_id" {
  description = "ID of the Clerk secret key in Key Vault"
  value       = azurerm_key_vault_secret.clerk_secret_key.id
}

output "clerk_webhook_signing_secret_id" {
  description = "ID of the Clerk webhook signing secret in Key Vault"
  value       = azurerm_key_vault_secret.clerk_webhook_signing_secret.id
}

output "postgres_admin_password_id" {
  description = "ID of the PostgreSQL admin password in Key Vault"
  value       = azurerm_key_vault_secret.postgres_admin_password.id
}

output "google_api_key_id" {
  description = "ID of the Google API key in Key Vault (if provided)"
  value       = var.google_api_key != "" ? azurerm_key_vault_secret.google_api_key[0].id : null
}
