# -----------------------------------------------------------------------------
# Log Analytics & Application Insights
# -----------------------------------------------------------------------------
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-ltc-${var.environment}-${local.suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_application_insights" "main" {
  name                = "appi-ltc-${var.environment}-${local.suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
  tags                = local.tags
}

# -----------------------------------------------------------------------------
# Monitoring - Action Group
# -----------------------------------------------------------------------------
resource "azurerm_monitor_action_group" "critical" {
  name                = "ag-ltc-critical-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "ltccrit"
  tags                = local.tags

  email_receiver {
    name                    = "admin"
    email_address           = var.alert_email
    use_common_alert_schema = true
  }
}

# -----------------------------------------------------------------------------
# Monitoring - API Alerts
# -----------------------------------------------------------------------------

# Alert: API 5xx Errors (Sev1 - Critical)
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "api_5xx_errors" {
  name                = "alert-ltc-api-5xx-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when API returns 5xx errors"
  severity            = 1
  enabled             = true
  tags                = local.tags

  scopes                = [azurerm_application_insights.main.id]
  evaluation_frequency  = "PT5M"
  window_duration       = "PT5M"
  target_resource_types = ["microsoft.insights/components"]

  criteria {
    query = <<-QUERY
      requests
      | where resultCode startswith "5"
      | summarize ErrorCount = count() by bin(timestamp, 5m)
    QUERY
    time_aggregation_method = "Count"
    operator                = "GreaterThanOrEqual"
    threshold               = 1

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  action {
    action_groups = [azurerm_monitor_action_group.critical.id]
  }
}

# Alert: Container Restarts (Sev1 - Critical)
resource "azurerm_monitor_metric_alert" "api_restarts" {
  name                = "alert-ltc-api-restarts-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  description         = "Alert when API container restarts"
  severity            = 1
  enabled             = true
  tags                = local.tags

  scopes      = [azurerm_container_app.api.id]
  frequency   = "PT1M"
  window_size = "PT5M"

  criteria {
    metric_namespace = "Microsoft.App/containerApps"
    metric_name      = "RestartCount"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 0
  }

  action {
    action_group_id = azurerm_monitor_action_group.critical.id
  }
}

# Alert: API High CPU (Sev2 - Warning)
resource "azurerm_monitor_metric_alert" "api_high_cpu" {
  name                = "alert-ltc-api-cpu-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  description         = "Alert when API CPU exceeds 80%"
  severity            = 2
  enabled             = true
  tags                = local.tags

  scopes      = [azurerm_container_app.api.id]
  frequency   = "PT5M"
  window_size = "PT15M"

  criteria {
    metric_namespace = "Microsoft.App/containerApps"
    metric_name      = "UsageNanoCores"
    aggregation      = "Average"
    operator         = "GreaterThan"
    # 0.5 CPU allocated = 500,000,000 nanocores, 80% = 400,000,000
    threshold = 400000000
  }

  action {
    action_group_id = azurerm_monitor_action_group.critical.id
  }
}

# Alert: API High Memory (Sev2 - Warning)
resource "azurerm_monitor_metric_alert" "api_high_memory" {
  name                = "alert-ltc-api-memory-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  description         = "Alert when API memory exceeds 80%"
  severity            = 2
  enabled             = true
  tags                = local.tags

  scopes      = [azurerm_container_app.api.id]
  frequency   = "PT5M"
  window_size = "PT15M"

  criteria {
    metric_namespace = "Microsoft.App/containerApps"
    metric_name      = "WorkingSetBytes"
    aggregation      = "Average"
    operator         = "GreaterThan"
    # 1Gi allocated = 1073741824 bytes, 80% = 858993459
    threshold = 858993459
  }

  action {
    action_group_id = azurerm_monitor_action_group.critical.id
  }
}

# Alert: API High Latency (Sev2 - Warning)
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "api_high_latency" {
  name                = "alert-ltc-api-latency-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when API average response time exceeds 2 seconds"
  severity            = 2
  enabled             = true
  tags                = local.tags

  scopes                = [azurerm_application_insights.main.id]
  evaluation_frequency  = "PT5M"
  window_duration       = "PT5M"
  target_resource_types = ["microsoft.insights/components"]

  criteria {
    query = <<-QUERY
      requests
      | summarize AvgDuration = avg(duration) by bin(timestamp, 5m)
      | where AvgDuration > 2000
    QUERY
    time_aggregation_method = "Count"
    operator                = "GreaterThanOrEqual"
    threshold               = 1

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  action {
    action_groups = [azurerm_monitor_action_group.critical.id]
  }
}

# -----------------------------------------------------------------------------
# Monitoring - Database Alerts
# -----------------------------------------------------------------------------

# Alert: Database Connection Failures (Sev1 - Critical)
resource "azurerm_monitor_metric_alert" "db_connection_failures" {
  name                = "alert-ltc-db-connections-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  description         = "Alert when database has connection failures"
  severity            = 1
  enabled             = true
  tags                = local.tags

  scopes      = [azurerm_postgresql_flexible_server.main.id]
  frequency   = "PT1M"
  window_size = "PT5M"

  criteria {
    metric_namespace = "Microsoft.DBforPostgreSQL/flexibleServers"
    metric_name      = "connections_failed"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 0
  }

  action {
    action_group_id = azurerm_monitor_action_group.critical.id
  }
}

# Alert: Database Storage >80% (Sev2 - Warning)
resource "azurerm_monitor_metric_alert" "db_storage" {
  name                = "alert-ltc-db-storage-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  description         = "Alert when database storage exceeds 80%"
  severity            = 2
  enabled             = true
  tags                = local.tags

  scopes      = [azurerm_postgresql_flexible_server.main.id]
  frequency   = "PT15M"
  window_size = "PT1H"

  criteria {
    metric_namespace = "Microsoft.DBforPostgreSQL/flexibleServers"
    metric_name      = "storage_percent"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 80
  }

  action {
    action_group_id = azurerm_monitor_action_group.critical.id
  }
}

# Alert: Database High CPU (Sev2 - Warning)
resource "azurerm_monitor_metric_alert" "db_high_cpu" {
  name                = "alert-ltc-db-cpu-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  description         = "Alert when database CPU exceeds 80%"
  severity            = 2
  enabled             = true
  tags                = local.tags

  scopes      = [azurerm_postgresql_flexible_server.main.id]
  frequency   = "PT5M"
  window_size = "PT15M"

  criteria {
    metric_namespace = "Microsoft.DBforPostgreSQL/flexibleServers"
    metric_name      = "cpu_percent"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 80
  }

  action {
    action_group_id = azurerm_monitor_action_group.critical.id
  }
}

# -----------------------------------------------------------------------------
# Monitoring - Smart Detection (AI-powered anomaly detection)
# -----------------------------------------------------------------------------
# Azure automatically creates a FailureAnomaliesDetector when Application Insights
# is created. We import and manage the existing one to link our action group.
# The name follows Azure's convention: "Failure Anomalies - {app_insights_name}"

resource "azurerm_monitor_smart_detector_alert_rule" "failure_anomalies" {
  name                = "Failure Anomalies - ${azurerm_application_insights.main.name}"
  resource_group_name = azurerm_resource_group.main.name
  description         = "Failure Anomalies notifies you of an unusual rise in the rate of failed HTTP requests or dependency calls."
  severity            = "Sev3"
  frequency           = "PT1M"
  detector_type       = "FailureAnomaliesDetector"
  scope_resource_ids  = [azurerm_application_insights.main.id]

  action_group {
    ids = [azurerm_monitor_action_group.critical.id]
  }

  lifecycle {
    # Prevent Terraform from trying to recreate if Azure changes the description
    ignore_changes = [description]
  }
}

# -----------------------------------------------------------------------------
# Monitoring - Dashboard
# -----------------------------------------------------------------------------
resource "azurerm_portal_dashboard" "main" {
  name                = "dash-ltc-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.tags

  dashboard_properties = jsonencode({
    lenses = {
      "0" = {
        order = 0
        parts = {
          "0" = {
            position = { x = 0, y = 0, colSpan = 6, rowSpan = 4 }
            metadata = {
              type = "Extension/HubsExtension/PartType/MonitorChartPart"
              inputs = [
                {
                  name = "options"
                  value = {
                    chart = {
                      title = "API Request Rate"
                      metrics = [{
                        resourceMetadata = { id = azurerm_application_insights.main.id }
                        name             = "requests/count"
                        aggregationType  = 7
                        namespace        = "microsoft.insights/components"
                      }]
                      visualization = { chartType = 2 }
                      timespan      = { relative = { duration = 86400000 } }
                    }
                  }
                }
              ]
            }
          }
          "1" = {
            position = { x = 6, y = 0, colSpan = 6, rowSpan = 4 }
            metadata = {
              type = "Extension/HubsExtension/PartType/MonitorChartPart"
              inputs = [
                {
                  name = "options"
                  value = {
                    chart = {
                      title = "API Failed Requests"
                      metrics = [{
                        resourceMetadata = { id = azurerm_application_insights.main.id }
                        name             = "requests/failed"
                        aggregationType  = 7
                        namespace        = "microsoft.insights/components"
                      }]
                      visualization = { chartType = 2 }
                      timespan      = { relative = { duration = 86400000 } }
                    }
                  }
                }
              ]
            }
          }
          "2" = {
            position = { x = 0, y = 4, colSpan = 6, rowSpan = 4 }
            metadata = {
              type = "Extension/HubsExtension/PartType/MonitorChartPart"
              inputs = [
                {
                  name = "options"
                  value = {
                    chart = {
                      title = "API Response Time (avg)"
                      metrics = [{
                        resourceMetadata = { id = azurerm_application_insights.main.id }
                        name             = "requests/duration"
                        aggregationType  = 4
                        namespace        = "microsoft.insights/components"
                      }]
                      visualization = { chartType = 2 }
                      timespan      = { relative = { duration = 86400000 } }
                    }
                  }
                }
              ]
            }
          }
          "3" = {
            position = { x = 6, y = 4, colSpan = 6, rowSpan = 4 }
            metadata = {
              type = "Extension/HubsExtension/PartType/MonitorChartPart"
              inputs = [
                {
                  name = "options"
                  value = {
                    chart = {
                      title = "Database CPU %"
                      metrics = [{
                        resourceMetadata = { id = azurerm_postgresql_flexible_server.main.id }
                        name             = "cpu_percent"
                        aggregationType  = 4
                        namespace        = "Microsoft.DBforPostgreSQL/flexibleServers"
                      }]
                      visualization = { chartType = 2 }
                      timespan      = { relative = { duration = 86400000 } }
                    }
                  }
                }
              ]
            }
          }
          "4" = {
            position = { x = 0, y = 8, colSpan = 6, rowSpan = 4 }
            metadata = {
              type = "Extension/HubsExtension/PartType/MonitorChartPart"
              inputs = [
                {
                  name = "options"
                  value = {
                    chart = {
                      title = "Database Connections"
                      metrics = [{
                        resourceMetadata = { id = azurerm_postgresql_flexible_server.main.id }
                        name             = "active_connections"
                        aggregationType  = 4
                        namespace        = "Microsoft.DBforPostgreSQL/flexibleServers"
                      }]
                      visualization = { chartType = 2 }
                      timespan      = { relative = { duration = 86400000 } }
                    }
                  }
                }
              ]
            }
          }
          "5" = {
            position = { x = 6, y = 8, colSpan = 6, rowSpan = 4 }
            metadata = {
              type = "Extension/HubsExtension/PartType/MonitorChartPart"
              inputs = [
                {
                  name = "options"
                  value = {
                    chart = {
                      title = "Database Storage %"
                      metrics = [{
                        resourceMetadata = { id = azurerm_postgresql_flexible_server.main.id }
                        name             = "storage_percent"
                        aggregationType  = 4
                        namespace        = "Microsoft.DBforPostgreSQL/flexibleServers"
                      }]
                      visualization = { chartType = 2 }
                      timespan      = { relative = { duration = 86400000 } }
                    }
                  }
                }
              ]
            }
          }
        }
      }
    }
    metadata = {
      model = {
        timeRange = {
          type  = "MsPortalFx.Composition.Configuration.ValueTypes.TimeRange"
          value = { relative = { duration = 24, timeUnit = 1 } }
        }
      }
    }
  })
}
