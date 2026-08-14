# None of these resource types expose Azure Monitor category groups, so each log
// category is named explicitly.
resource "azurerm_monitor_diagnostic_setting" "key_vault" {
  name                       = "diag-to-log-analytics"
  target_resource_id         = azurerm_key_vault.main.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  enabled_log {
    category = "AuditEvent"
  }
}

resource "azurerm_monitor_diagnostic_setting" "container_registry" {
  name                       = "diag-to-log-analytics"
  target_resource_id         = azurerm_container_registry.main.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  enabled_log {
    category = "ContainerRegistryLoginEvents"
  }

  enabled_log {
    category = "ContainerRegistryRepositoryEvents"
  }
}

resource "azurerm_monitor_diagnostic_setting" "postgres" {
  name                       = "diag-to-log-analytics"
  target_resource_id         = azurerm_postgresql_flexible_server.main.id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  enabled_log {
    category = "PostgreSQLLogs"
  }
}

# Data-plane reads and writes against the deployment container. This is the only
# audit trail for the Functions storage account, so it stays on even though the
# account is expected to be low traffic.
resource "azurerm_monitor_diagnostic_setting" "verification_functions_storage_blob" {
  name                       = "diag-to-log-analytics"
  target_resource_id         = "${azurerm_storage_account.verification_functions.id}/blobServices/default"
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  enabled_log {
    category = "StorageWrite"
  }

  enabled_log {
    category = "StorageDelete"
  }
}
