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

resource "azurerm_monitor_action_group" "critical" {
  name                = "ag-ltc-critical-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "ltccrit"
  tags                = local.tags

  dynamic "email_receiver" {
    for_each = var.alert_emails
    content {
      name                    = "alert-${email_receiver.key}"
      email_address           = email_receiver.value
      use_common_alert_schema = true
    }
  }
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "api_5xx_errors" {
  name                = "alert-ltc-api-5xx-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when API returns 3+ 5xx errors in a 5-minute window"
  severity            = 1
  enabled             = true
  tags                = local.tags

  scopes                = [azurerm_application_insights.main.id]
  evaluation_frequency  = "PT5M"
  window_duration       = "PT5M"
  target_resource_types = ["microsoft.insights/components"]

  criteria {
    query                   = <<-QUERY
      requests
      | where resultCode startswith "5"
      | summarize ErrorCount = count() by bin(timestamp, 5m)
    QUERY
    time_aggregation_method = "Count"
    operator                = "GreaterThanOrEqual"
    threshold               = 3

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 2
      number_of_evaluation_periods             = 3
    }
  }

  action {
    action_groups = [azurerm_monitor_action_group.critical.id]
  }
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "migration_failure" {
  name                = "alert-ltc-init-failed-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when app startup or migration fails (init.failed log event)"
  severity            = 1
  enabled             = true
  tags                = local.tags

  scopes                = [azurerm_application_insights.main.id]
  evaluation_frequency  = "PT5M"
  window_duration       = "PT5M"
  target_resource_types = ["microsoft.insights/components"]

  criteria {
    query                   = <<-QUERY
      traces
      | where message has "init.failed"
      | summarize Count = count() by bin(timestamp, 5m)
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

# Dashboard layout (12-column grid):
#   Row 0: Failed Requests | Response Time Percentiles
#   Row 4: Database CPU % | Active Users & Request Volume
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
          # --- Row 0: Errors + Latency ---
          "0" = {
            position = { x = 0, y = 0, colSpan = 6, rowSpan = 4 }
            metadata = {
              type = "Extension/HubsExtension/PartType/MonitorChartPart"
              inputs = [
                {
                  name = "options"
                  value = {
                    chart = {
                      title = "Failed Requests (4xx + 5xx)"
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
          "1" = {
            position = { x = 6, y = 0, colSpan = 6, rowSpan = 4 }
            metadata = {
              type = "Extension/Microsoft_OperationsManagementSuite_Workspace/PartType/LogsDashboardPart"
              inputs = [
                {
                  name       = "resourceTypeMode"
                  isOptional = true
                },
                {
                  name = "ComponentId"
                  value = {
                    ResourceId = azurerm_application_insights.main.id
                  }
                  isOptional = true
                },
                {
                  name = "Scope"
                  value = {
                    resourceIds = [azurerm_application_insights.main.id]
                  }
                  isOptional = true
                },
                {
                  name       = "PartId"
                  value      = "a1b2c3d4-0001-4000-8000-000000000002"
                  isOptional = true
                },
                {
                  name       = "Version"
                  value      = "2.0"
                  isOptional = true
                },
                {
                  name       = "TimeRange"
                  value      = "PT24H"
                  isOptional = true
                },
                {
                  name       = "DashboardId"
                  isOptional = true
                },
                {
                  name       = "DraftRequestParameters"
                  isOptional = true
                },
                {
                  name       = "Query"
                  value      = "requests | summarize P50=percentile(duration, 50), P95=percentile(duration, 95), P99=percentile(duration, 99) by bin(timestamp, 5m) | render timechart"
                  isOptional = true
                },
                {
                  name       = "ControlType"
                  value      = "FrameControlChart"
                  isOptional = true
                },
                {
                  name       = "SpecificChart"
                  value      = "Line"
                  isOptional = true
                },
                {
                  name       = "PartTitle"
                  value      = "Response Time Percentiles (P50 / P95 / P99)"
                  isOptional = true
                },
                {
                  name       = "IsQueryContainTimeRange"
                  value      = false
                  isOptional = true
                },
                {
                  name = "Dimensions"
                  value = {
                    xAxis = { name = "timestamp", type = "datetime" }
                    yAxis = [
                      { name = "P50", type = "real" },
                      { name = "P95", type = "real" },
                      { name = "P99", type = "real" }
                    ]
                    splitBy     = []
                    aggregation = "Sum"
                  }
                  isOptional = true
                },
                {
                  name       = "LegendOptions"
                  isOptional = true
                }
              ]
              settings = {}
            }
          }
          # --- Row 4: Infrastructure + Usage ---
          "2" = {
            position = { x = 0, y = 4, colSpan = 6, rowSpan = 4 }
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
          "3" = {
            position = { x = 6, y = 4, colSpan = 6, rowSpan = 4 }
            metadata = {
              type = "Extension/Microsoft_OperationsManagementSuite_Workspace/PartType/LogsDashboardPart"
              inputs = [
                {
                  name       = "resourceTypeMode"
                  isOptional = true
                },
                {
                  name = "ComponentId"
                  value = {
                    ResourceId = azurerm_application_insights.main.id
                  }
                  isOptional = true
                },
                {
                  name = "Scope"
                  value = {
                    resourceIds = [azurerm_application_insights.main.id]
                  }
                  isOptional = true
                },
                {
                  name       = "PartId"
                  value      = "a1b2c3d4-0001-4000-8000-000000000009"
                  isOptional = true
                },
                {
                  name       = "Version"
                  value      = "2.0"
                  isOptional = true
                },
                {
                  name       = "TimeRange"
                  value      = "PT24H"
                  isOptional = true
                },
                {
                  name       = "DashboardId"
                  isOptional = true
                },
                {
                  name       = "DraftRequestParameters"
                  isOptional = true
                },
                {
                  name       = "Query"
                  value      = "requests | where timestamp > ago(24h) | where name !has 'health' and name !has 'static' | summarize UniqueUsers=dcount(user_AuthenticatedId), Requests=count() by bin(timestamp, 1h) | render timechart"
                  isOptional = true
                },
                {
                  name       = "ControlType"
                  value      = "FrameControlChart"
                  isOptional = true
                },
                {
                  name       = "SpecificChart"
                  value      = "Line"
                  isOptional = true
                },
                {
                  name       = "PartTitle"
                  value      = "Active Users & Request Volume (hourly)"
                  isOptional = true
                },
                {
                  name       = "IsQueryContainTimeRange"
                  value      = true
                  isOptional = true
                },
                {
                  name = "Dimensions"
                  value = {
                    xAxis = { name = "timestamp", type = "datetime" }
                    yAxis = [
                      { name = "UniqueUsers", type = "long" },
                      { name = "Requests", type = "long" }
                    ]
                    splitBy     = []
                    aggregation = "Sum"
                  }
                  isOptional = true
                },
                {
                  name       = "LegendOptions"
                  isOptional = true
                }
              ]
              settings = {}
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
