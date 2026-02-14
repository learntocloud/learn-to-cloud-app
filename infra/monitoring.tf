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

  dynamic "email_receiver" {
    for_each = var.alert_emails
    content {
      name                    = "alert-${email_receiver.key}"
      email_address           = email_receiver.value
      use_common_alert_schema = true
    }
  }
}

# Action Group for Warning alerts (Sev2) - email only, no paging
# For Slack integration, add webhook_receiver with var.slack_webhook_url
resource "azurerm_monitor_action_group" "warning" {
  name                = "ag-ltc-warning-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "ltcwarn"
  tags                = local.tags

  dynamic "email_receiver" {
    for_each = var.alert_emails
    content {
      name                    = "alert-${email_receiver.key}"
      email_address           = email_receiver.value
      use_common_alert_schema = true
    }
  }

  # Optional Slack webhook for warning notifications
  dynamic "webhook_receiver" {
    for_each = var.slack_webhook_url != "" ? [1] : []
    content {
      name                    = "slack"
      service_uri             = var.slack_webhook_url
      use_common_alert_schema = true
    }
  }
}

# -----------------------------------------------------------------------------
# Monitoring - API Alerts
# -----------------------------------------------------------------------------

# Alert: API 5xx Errors (Sev1 - Critical)
# Threshold ≥3 with 2/3 failing periods to suppress single transient errors
# (e.g., one DB hiccup during a deploy) and reduce alert fatigue.
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

# Alert: Container Restarts (Sev1 - Critical)
# Threshold >2 to ignore normal deploy restarts while catching crash loops.
resource "azurerm_monitor_metric_alert" "api_restarts" {
  name                = "alert-ltc-api-restarts-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  description         = "Alert when API container restarts more than twice in 5 minutes (crash loop)"
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
    threshold        = 2
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
    action_group_id = azurerm_monitor_action_group.warning.id
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
    action_group_id = azurerm_monitor_action_group.warning.id
  }
}

# Alert: API High Latency P95 (Sev2 - Warning)
# Uses P95 instead of avg — avg hides tail latency that affects real users.
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "api_high_latency" {
  name                = "alert-ltc-api-latency-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when API P95 response time exceeds 3 seconds"
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
      | summarize P95Duration = percentile(duration, 95) by bin(timestamp, 5m)
      | where P95Duration > 3000
    QUERY
    time_aggregation_method = "Count"
    operator                = "GreaterThanOrEqual"
    threshold               = 1

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 2
      number_of_evaluation_periods             = 3
    }
  }

  action {
    action_groups = [azurerm_monitor_action_group.warning.id]
  }
}

# -----------------------------------------------------------------------------
# Monitoring - Database Alerts
# -----------------------------------------------------------------------------

# Alert: Database Connection Failures (Sev1 - Critical)
# Threshold >5 to suppress transient failures from pool expansion under burst load.
resource "azurerm_monitor_metric_alert" "db_connection_failures" {
  name                = "alert-ltc-db-connections-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  description         = "Alert when database has 5+ connection failures in 5 minutes"
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
    threshold        = 5
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
    action_group_id = azurerm_monitor_action_group.warning.id
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
    action_group_id = azurerm_monitor_action_group.warning.id
  }
}

# -----------------------------------------------------------------------------
# Monitoring - Dependency Alerts
# -----------------------------------------------------------------------------

# Alert: LLM / Azure OpenAI Dependency Failures (Sev1 - Critical)
# Code verification is a core feature — if OpenAI is down or rate-limiting,
# users can't verify their hands-on projects.
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "llm_dependency_failures" {
  name                = "alert-ltc-llm-failures-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when Azure OpenAI dependency calls fail (5+ in 5 min)"
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
      | where type == "HTTP" or type == "Azure OpenAI"
      | where target has "openai" or target has "oai-ltc"
      | where success == false
      | summarize FailureCount = count() by bin(timestamp, 5m)
    QUERY
    time_aggregation_method = "Count"
    operator                = "GreaterThanOrEqual"
    threshold               = 5

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  action {
    action_groups = [azurerm_monitor_action_group.critical.id]
  }
}

# Alert: 4xx Spike (Sev2 - Warning)
# A sudden jump in 401/403 could indicate auth misconfiguration (OAuth secrets
# rotated, session key mismatch). 404s are excluded since they're normal.
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "api_4xx_spike" {
  name                = "alert-ltc-api-4xx-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when API returns 20+ 401/403 errors in 5 minutes (possible auth breakage)"
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
      | where resultCode in ("401", "403")
      | summarize ErrorCount = count() by bin(timestamp, 5m)
    QUERY
    time_aggregation_method = "Count"
    operator                = "GreaterThanOrEqual"
    threshold               = 20

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 2
      number_of_evaluation_periods             = 3
    }
  }

  action {
    action_groups = [azurerm_monitor_action_group.warning.id]
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
# Layout (12-column grid):
#   Row 0  : Request Rate | Failed Requests (by status code)
#   Row 4  : P95 Response Time | Response Time by Route (top 5 slowest)
#   Row 8  : Replica Count | LLM Dependency Latency & Failures
#   Row 12 : DB CPU % | DB Connections (vs 35 max on B1ms)
#   Row 16 : DB Storage % | Active Users (unique authenticated sessions)
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
          # --- Row 0: Traffic Overview ---
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
          # --- Row 4: Latency ---
          "2" = {
            position = { x = 0, y = 4, colSpan = 6, rowSpan = 4 }
            metadata = {
              type = "Extension/Microsoft_OperationsManagementSuite_Workspace/PartType/LogsDashboardPart"
              inputs = [
                {
                  name       = "resourceTypeMode"
                  isOptional = true
                },
                {
                  name  = "ComponentId"
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
                }
              ]
              settings = {}
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
                  name  = "ComponentId"
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
                  value      = "a1b2c3d4-0001-4000-8000-000000000003"
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
                  value      = "requests | where timestamp > ago(24h) | summarize P95=percentile(duration, 95), Count=count() by name | top 10 by P95 desc | project Route=name, P95_ms=round(P95, 0), Requests=Count"
                  isOptional = true
                },
                {
                  name       = "ControlType"
                  value      = "AnalyticsGrid"
                  isOptional = true
                },
                {
                  name       = "PartTitle"
                  value      = "Slowest Routes (P95 latency)"
                  isOptional = true
                },
                {
                  name       = "IsQueryContainTimeRange"
                  value      = true
                  isOptional = true
                }
              ]
              settings = {}
            }
          }
          # --- Row 8: Container App + LLM Dependency ---
          "4" = {
            position = { x = 0, y = 8, colSpan = 6, rowSpan = 4 }
            metadata = {
              type = "Extension/HubsExtension/PartType/MonitorChartPart"
              inputs = [
                {
                  name = "options"
                  value = {
                    chart = {
                      title = "Container App Replica Count"
                      metrics = [{
                        resourceMetadata = { id = azurerm_container_app.api.id }
                        name             = "Replicas"
                        aggregationType  = 3
                        namespace        = "Microsoft.App/containerApps"
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
              type = "Extension/Microsoft_OperationsManagementSuite_Workspace/PartType/LogsDashboardPart"
              inputs = [
                {
                  name       = "resourceTypeMode"
                  isOptional = true
                },
                {
                  name  = "ComponentId"
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
                  value      = "a1b2c3d4-0001-4000-8000-000000000005"
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
                  value      = "dependencies | where target has 'openai' or target has 'oai-ltc' | summarize Calls=count(), Failures=countif(success == false), AvgDuration=avg(duration) by bin(timestamp, 15m) | render timechart"
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
                  value      = "LLM / OpenAI Dependency (calls, failures, latency)"
                  isOptional = true
                },
                {
                  name       = "IsQueryContainTimeRange"
                  value      = false
                  isOptional = true
                }
              ]
              settings = {}
            }
          }
          # --- Row 12: Database ---
          "6" = {
            position = { x = 0, y = 12, colSpan = 6, rowSpan = 4 }
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
          "7" = {
            position = { x = 6, y = 12, colSpan = 6, rowSpan = 4 }
            metadata = {
              type = "Extension/HubsExtension/PartType/MonitorChartPart"
              inputs = [
                {
                  name = "options"
                  value = {
                    chart = {
                      title = "Database Active Connections (max 35 on B1ms)"
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
          # --- Row 16: Storage + User Activity ---
          "8" = {
            position = { x = 0, y = 16, colSpan = 6, rowSpan = 4 }
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
          "9" = {
            position = { x = 6, y = 16, colSpan = 6, rowSpan = 4 }
            metadata = {
              type = "Extension/Microsoft_OperationsManagementSuite_Workspace/PartType/LogsDashboardPart"
              inputs = [
                {
                  name       = "resourceTypeMode"
                  isOptional = true
                },
                {
                  name  = "ComponentId"
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
                }
              ]
              settings = {}
            }
          }
          # --- Row 20: Error Breakdown + GitHub Dependency ---
          "10" = {
            position = { x = 0, y = 20, colSpan = 6, rowSpan = 4 }
            metadata = {
              type = "Extension/Microsoft_OperationsManagementSuite_Workspace/PartType/LogsDashboardPart"
              inputs = [
                {
                  name       = "resourceTypeMode"
                  isOptional = true
                },
                {
                  name  = "ComponentId"
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
                  value      = "a1b2c3d4-0001-4000-8000-000000000010"
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
                  value      = "requests | where timestamp > ago(24h) | where toint(resultCode) >= 400 | summarize Count=count() by resultCode, name | top 15 by Count desc | project Status=resultCode, Route=name, Count"
                  isOptional = true
                },
                {
                  name       = "ControlType"
                  value      = "AnalyticsGrid"
                  isOptional = true
                },
                {
                  name       = "PartTitle"
                  value      = "Error Breakdown (status code × route)"
                  isOptional = true
                },
                {
                  name       = "IsQueryContainTimeRange"
                  value      = true
                  isOptional = true
                }
              ]
              settings = {}
            }
          }
          "11" = {
            position = { x = 6, y = 20, colSpan = 6, rowSpan = 4 }
            metadata = {
              type = "Extension/Microsoft_OperationsManagementSuite_Workspace/PartType/LogsDashboardPart"
              inputs = [
                {
                  name       = "resourceTypeMode"
                  isOptional = true
                },
                {
                  name  = "ComponentId"
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
                  value      = "a1b2c3d4-0001-4000-8000-000000000011"
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
                  value      = "dependencies | where target has 'github' | summarize Calls=count(), Failures=countif(success == false), AvgDuration=avg(duration) by bin(timestamp, 15m) | render timechart"
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
                  value      = "GitHub API Dependency (calls, failures, latency)"
                  isOptional = true
                },
                {
                  name       = "IsQueryContainTimeRange"
                  value      = false
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
