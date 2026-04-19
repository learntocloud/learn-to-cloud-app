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

# ---------------------------------------------------------------------------
# Metric Alerts — Database (B_Standard_B1ms: 1 vCore, 2 GB, burstable)
# ---------------------------------------------------------------------------

resource "azurerm_monitor_metric_alert" "db_cpu" {
  name                = "alert-ltc-db-cpu-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  description         = "PostgreSQL CPU sustained above 80% (burstable tier — may indicate credit exhaustion)"
  severity            = 2
  enabled             = true
  scopes              = [azurerm_postgresql_flexible_server.main.id]
  frequency           = "PT5M"
  window_size         = "PT15M"
  tags                = local.tags

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

resource "azurerm_monitor_metric_alert" "db_storage" {
  name                = "alert-ltc-db-storage-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  description         = "PostgreSQL storage usage above 85% of 32 GB"
  severity            = 2
  enabled             = true
  scopes              = [azurerm_postgresql_flexible_server.main.id]
  frequency           = "PT15M"
  window_size         = "PT1H"
  tags                = local.tags

  criteria {
    metric_namespace = "Microsoft.DBforPostgreSQL/flexibleServers"
    metric_name      = "storage_percent"
    aggregation      = "Maximum"
    operator         = "GreaterThan"
    threshold        = 85
  }

  action {
    action_group_id = azurerm_monitor_action_group.critical.id
  }
}

resource "azurerm_monitor_metric_alert" "db_connections" {
  name                = "alert-ltc-db-connections-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  description         = "PostgreSQL active connections above 30 (B1ms max is 50; 35 user connections)"
  severity            = 1
  enabled             = true
  scopes              = [azurerm_postgresql_flexible_server.main.id]
  frequency           = "PT5M"
  window_size         = "PT5M"
  tags                = local.tags

  criteria {
    metric_namespace = "Microsoft.DBforPostgreSQL/flexibleServers"
    metric_name      = "active_connections"
    aggregation      = "Maximum"
    operator         = "GreaterThan"
    threshold        = 30
  }

  action {
    action_group_id = azurerm_monitor_action_group.critical.id
  }
}

resource "azurerm_monitor_metric_alert" "db_credits" {
  name                = "alert-ltc-db-credits-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  description         = "PostgreSQL burstable CPU credits nearly exhausted (< 10 remaining)"
  severity            = 1
  enabled             = true
  scopes              = [azurerm_postgresql_flexible_server.main.id]
  frequency           = "PT5M"
  window_size         = "PT5M"
  tags                = local.tags

  criteria {
    metric_namespace = "Microsoft.DBforPostgreSQL/flexibleServers"
    metric_name      = "cpu_credits_remaining"
    aggregation      = "Minimum"
    operator         = "LessThan"
    threshold        = 10
  }

  action {
    action_group_id = azurerm_monitor_action_group.critical.id
  }
}

# ---------------------------------------------------------------------------
# Metric Alerts — Container App (0.5 CPU / 1 Gi memory, 1–2 replicas)
# ---------------------------------------------------------------------------

resource "azurerm_monitor_metric_alert" "api_cpu" {
  name                = "alert-ltc-api-cpu-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  description         = "Container App CPU above 80% of 0.5 cores (400M nanocores)"
  severity            = 2
  enabled             = true
  scopes              = [azurerm_container_app.api.id]
  frequency           = "PT5M"
  window_size         = "PT5M"
  tags                = local.tags

  criteria {
    metric_namespace = "Microsoft.App/containerApps"
    metric_name      = "UsageNanoCores"
    aggregation      = "Maximum"
    operator         = "GreaterThan"
    threshold        = 400000000
  }

  action {
    action_group_id = azurerm_monitor_action_group.critical.id
  }
}

resource "azurerm_monitor_metric_alert" "api_memory" {
  name                = "alert-ltc-api-memory-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  description         = "Container App memory above 80% of 1 Gi (858993459 bytes)"
  severity            = 2
  enabled             = true
  scopes              = [azurerm_container_app.api.id]
  frequency           = "PT5M"
  window_size         = "PT5M"
  tags                = local.tags

  criteria {
    metric_namespace = "Microsoft.App/containerApps"
    metric_name      = "WorkingSetBytes"
    aggregation      = "Maximum"
    operator         = "GreaterThan"
    threshold        = 858993459
  }

  action {
    action_group_id = azurerm_monitor_action_group.critical.id
  }
}

# ---------------------------------------------------------------------------
# Availability Test — /ready endpoint
# ---------------------------------------------------------------------------

resource "azurerm_application_insights_standard_web_test" "readiness" {
  name                    = "webtest-ltc-ready-${var.environment}"
  resource_group_name     = azurerm_resource_group.main.name
  location                = azurerm_resource_group.main.location
  application_insights_id = azurerm_application_insights.main.id
  description             = "Synthetic readiness probe — checks /ready (init + DB connectivity)"
  enabled                 = true
  frequency               = 300
  timeout                 = 30
  retry_enabled           = true
  tags                    = local.tags

  geo_locations = [
    "us-va-ash-azr",  # East US
    "emea-nl-ams-azr", # West Europe
    "apac-sg-sin-azr"  # Southeast Asia
  ]

  request {
    url = "https://${azurerm_container_app.api.ingress[0].fqdn}/ready"
  }

  validation_rules {
    expected_status_code = 200
  }
}

resource "azurerm_monitor_metric_alert" "availability" {
  name                = "alert-ltc-availability-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  description         = "Availability test failures — app unreachable from 2+ geo locations"
  severity            = 0
  enabled             = true
  scopes              = [azurerm_application_insights.main.id]
  frequency           = "PT5M"
  window_size         = "PT5M"
  tags                = local.tags

  application_insights_web_test_location_availability_criteria {
    web_test_id           = azurerm_application_insights_standard_web_test.readiness.id
    component_id          = azurerm_application_insights.main.id
    failed_location_count = 2
  }

  action {
    action_group_id = azurerm_monitor_action_group.critical.id
  }
}

# ---------------------------------------------------------------------------
# Log Alerts (scheduled query rules v2)
# ---------------------------------------------------------------------------

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

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "api_latency" {
  name                = "alert-ltc-api-latency-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when API P95 latency exceeds 500ms over a 5-minute window"
  severity            = 2
  enabled             = true
  tags                = local.tags

  scopes                = [azurerm_application_insights.main.id]
  evaluation_frequency  = "PT5M"
  window_duration       = "PT5M"
  target_resource_types = ["microsoft.insights/components"]

  criteria {
    query                   = <<-QUERY
      requests
      | summarize P95Ms = percentile(duration, 95) / 1ms by bin(timestamp, 5m)
    QUERY
    time_aggregation_method = "Maximum"
    operator                = "GreaterThan"
    threshold               = 500
    metric_measure_column   = "P95Ms"

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 2
      number_of_evaluation_periods             = 3
    }
  }

  action {
    action_groups = [azurerm_monitor_action_group.critical.id]
  }
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "api_4xx_errors" {
  name                = "alert-ltc-api-4xx-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when API returns 50+ client errors (4xx) in a 5-minute window"
  severity            = 2
  enabled             = true
  tags                = local.tags

  scopes                = [azurerm_application_insights.main.id]
  evaluation_frequency  = "PT5M"
  window_duration       = "PT5M"
  target_resource_types = ["microsoft.insights/components"]

  criteria {
    query                   = <<-QUERY
      requests
      | where toint(resultCode) >= 400 and toint(resultCode) < 500
      | summarize ErrorCount = count() by bin(timestamp, 5m)
    QUERY
    time_aggregation_method = "Maximum"
    operator                = "GreaterThanOrEqual"
    threshold               = 50
    metric_measure_column   = "ErrorCount"

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 2
      number_of_evaluation_periods             = 3
    }
  }

  action {
    action_groups = [azurerm_monitor_action_group.critical.id]
  }
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "llm_failures" {
  name                = "alert-ltc-llm-failures-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when Azure OpenAI dependency failures exceed 5 in a 5-minute window"
  severity            = 1
  enabled             = true
  tags                = local.tags

  scopes                = [azurerm_application_insights.main.id]
  evaluation_frequency  = "PT5M"
  window_duration       = "PT5M"
  target_resource_types = ["microsoft.insights/components"]

  criteria {
    query                   = <<-QUERY
      dependencies
      | where type == "HTTP" and target has "openai" and success == false
      | summarize FailCount = count()
    QUERY
    time_aggregation_method = "Maximum"
    operator                = "GreaterThanOrEqual"
    threshold               = 5
    metric_measure_column   = "FailCount"

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  action {
    action_groups = [azurerm_monitor_action_group.critical.id]
  }
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "api_restarts" {
  name                = "alert-ltc-api-restarts-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when container crashes or restarts detected in system logs"
  severity            = 1
  enabled             = true
  tags                = local.tags

  scopes                = [azurerm_log_analytics_workspace.main.id]
  evaluation_frequency  = "PT5M"
  window_duration       = "PT15M"
  target_resource_types = ["microsoft.operationalinsights/workspaces"]

  criteria {
    query                   = <<-QUERY
      ContainerAppSystemLogs_CL
      | where ContainerAppName_s == "ca-ltc-api-${var.environment}"
      | where Reason_s in ("ContainerCrashing", "BackOff", "CrashLoopBackOff", "OOMKilled")
      | summarize CrashCount = count()
    QUERY
    time_aggregation_method = "Maximum"
    operator                = "GreaterThanOrEqual"
    threshold               = 2
    metric_measure_column   = "CrashCount"

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
