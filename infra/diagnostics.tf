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
