resource "azurerm_postgresql_flexible_server" "main" {
  name                          = "psql-ltc-${var.environment}-${local.suffix}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  version                       = "16"
  storage_mb                    = 32768
  sku_name                      = "B_Standard_B2s"
  backup_retention_days         = 7
  geo_redundant_backup_enabled  = false
  public_network_access_enabled = true
  zone                          = "3"
  tags                          = local.tags

  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false
  }
}

resource "azurerm_postgresql_flexible_server_database" "main" {
  name      = "learntocloud"
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "allow_azure" {
  name             = "AllowAzureServices"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# Entra admin is the API's managed identity (not a human user)
resource "azurerm_postgresql_flexible_server_active_directory_administrator" "api" {
  server_name         = azurerm_postgresql_flexible_server.main.name
  resource_group_name = azurerm_resource_group.main.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  object_id           = azurerm_user_assigned_identity.api.principal_id
  principal_name      = azurerm_user_assigned_identity.api.name
  principal_type      = "ServicePrincipal"
}
