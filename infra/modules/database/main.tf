# Database Module: PostgreSQL Flexible Server

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

# PostgreSQL Flexible Server
resource "azurerm_postgresql_flexible_server" "main" {
  name                = "psql-${var.app_name}-${var.environment}-${var.unique_suffix}"
  location            = var.location
  resource_group_name = var.resource_group_name

  sku_name        = "B_Standard_B1ms"
  version         = "16"
  storage_mb      = 32768
  auto_grow_enabled = true
  zone            = "3"

  administrator_login    = "ltcadmin"
  administrator_password = var.postgres_admin_password

  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false  # Using Entra ID auth only
  }

  backup_retention_days        = 7
  geo_redundant_backup_enabled = false

  # Note: high_availability block is omitted when HA is disabled

  tags = var.tags
}

# PostgreSQL Database
resource "azurerm_postgresql_flexible_server_database" "main" {
  name      = "learntocloud"
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# Firewall Rule - Allow Azure Services
resource "azurerm_postgresql_flexible_server_firewall_rule" "allow_azure_services" {
  name             = "AllowAzureServices"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}
