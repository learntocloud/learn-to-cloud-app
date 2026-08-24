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

resource "azurerm_application_insights" "frontend" {
  name                = "appi-ltc-frontend-${var.environment}-${local.suffix}"
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
# Availability test (synthetic uptime probe)
# ---------------------------------------------------------------------------

# Every alert below is a scheduled query over telemetry the app emits while it
# is running, so none of them fire on a "hard down" outage: a boot crashloop, an
# ingress/TLS/DNS breakage, or a full platform outage where zero telemetry
# flows. This standard web test is the one signal that pings the app from
# outside and pages when it is completely unreachable.
#
# It targets /health (pure liveness, always 200) and NOT /ready, which returns
# 503 on transient DB/schema issues that already have their own alerts; pointing
# the availability test at /ready would double-page and add noise.
resource "azurerm_application_insights_standard_web_test" "availability" {
  name                    = "webtest-ltc-availability-${var.environment}"
  resource_group_name     = azurerm_resource_group.main.name
  location                = azurerm_resource_group.main.location
  application_insights_id = azurerm_application_insights.main.id
  description             = "Synthetic uptime probe against https://learntocloud.guide/health"
  enabled                 = true
  frequency               = 300
  timeout                 = 30
  retry_enabled           = true
  tags                    = local.tags

  # Central US (Chicago) + West US (San Jose). Two regions is enough coverage
  # for a dev learning platform; full 3+ geo coverage is out of scope.
  geo_locations = ["us-il-ch1-azr", "us-ca-sjc-azr"]

  request {
    url                              = "https://learntocloud.guide/health"
    http_verb                        = "GET"
    parse_dependent_requests_enabled = false
    follow_redirects_enabled         = true
  }

  validation_rules {
    expected_status_code = 200
    ssl_check_enabled    = true
  }
}

resource "azurerm_monitor_metric_alert" "availability" {
  name                = "alert-ltc-availability-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  description         = "Alert when the availability web test reports less than 100% success (API unreachable)"
  severity            = 1
  enabled             = true
  frequency           = "PT5M"
  window_size         = "PT5M"
  tags                = local.tags

  # A metric alert can only span a single target resource type. Scope it to the
  # App Insights component (where the availabilityResults metric lands) and set
  # target_resource_type/location explicitly; mixing the web-test resource type
  # into scopes makes Azure reject the alert with a 400.
  scopes                   = [azurerm_application_insights.main.id]
  target_resource_type     = "microsoft.insights/components"
  target_resource_location = azurerm_resource_group.main.location

  criteria {
    metric_namespace = "microsoft.insights/components"
    metric_name      = "availabilityResults/availabilityPercentage"
    aggregation      = "Average"
    operator         = "LessThan"
    threshold        = 100

    dimension {
      name     = "availabilityResult/name"
      operator = "Include"
      values   = [azurerm_application_insights_standard_web_test.availability.name]
    }
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
      | where cloud_RoleName in ("learn-to-cloud-api", "ca-ltc-api-${var.environment}")
          or cloud_RoleName has "learn-to-cloud-api"
          or cloud_RoleName has "ca-ltc-api"
      | where resultCode startswith "5"
      | summarize ErrorCount = count() by bin(timestamp, 5m)
    QUERY
    time_aggregation_method = "Maximum"
    metric_measure_column   = "ErrorCount"
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

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "api_unhandled_exception" {
  name                = "alert-ltc-api-unhandled-exception-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert on the first exact unhandled API exception. Response guide: https://github.com/learntocloud/learn-to-cloud-app/blob/main/docs/runbooks/alerts.md#unhandled-api-exception"
  severity            = 1
  enabled             = true
  tags                = local.tags

  scopes                = [azurerm_application_insights.main.id]
  evaluation_frequency  = "PT5M"
  window_duration       = "PT5M"
  target_resource_types = ["microsoft.insights/components"]

  criteria {
    query                   = <<-QUERY
      exceptions
      | where cloud_RoleName == "learn-to-cloud-api"
      | where outerMessage == "unhandled.exception"
      | summarize CrashCount = count() by bin(timestamp, 5m)
    QUERY
    time_aggregation_method = "Maximum"
    metric_measure_column   = "CrashCount"
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

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "api_telemetry_pipeline_failure" {
  name                = "alert-ltc-api-telemetry-pipeline-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Detects API telemetry setup or transmission failures; it does not prove permanent telemetry loss or an Azure service fault. Response guide: https://github.com/learntocloud/learn-to-cloud-app/blob/main/docs/runbooks/alerts.md#telemetry-pipeline-failure"
  severity            = 1
  enabled             = true
  tags                = local.tags

  scopes                = [azurerm_log_analytics_workspace.main.id]
  evaluation_frequency  = "PT5M"
  window_duration       = "PT15M"
  target_resource_types = ["Microsoft.OperationalInsights/workspaces"]

  criteria {
    query                   = <<-QUERY
      ContainerAppConsoleLogs_CL
      | where ContainerAppName_s == "ca-ltc-api-${var.environment}"
      | where ContainerName_s == "api"
      | extend ParsedLog = parse_json(Log_s)
      | extend
          Event = tostring(ParsedLog.event),
          Logger = tostring(ParsedLog.logger)
      | extend
          IsConfigureFailure = Event == "telemetry.configure.failed",
          IsMainExporterFailure = Logger == "azure.monitor.opentelemetry.exporter.export._base"
            and Log_s contains "Envelopes could not be exported and are not retryable:"
      | where IsConfigureFailure or IsMainExporterFailure
      | summarize
          ConfigureFailureCount = countif(IsConfigureFailure),
          ExportFailureCount = countif(IsMainExporterFailure)
      | where ConfigureFailureCount >= 1 or ExportFailureCount >= 3
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

# Page only for the final outcome PostgreSQL accepted for an attempt.
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "verification_attempt_system_error" {
  name                = "alert-ltc-verification-attempt-system-error-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when a saved verification attempt outcome is server_error or cancelled. Response guide: https://github.com/learntocloud/learn-to-cloud-app/blob/main/docs/runbooks/alerts.md#verification-final-failures"
  severity            = 2
  enabled             = true
  tags                = local.tags

  scopes                = [azurerm_application_insights.main.id]
  evaluation_frequency  = "PT5M"
  window_duration       = "PT5M"
  target_resource_types = ["microsoft.insights/components"]

  criteria {
    query                   = <<-QUERY
      traces
      | where cloud_RoleName in (
          "learn-to-cloud-api",
          "ca-ltc-api-${var.environment}",
          "learn-to-cloud-verification-functions",
          "func-ltc-verification-${var.environment}"
        )
          or cloud_RoleName has "learn-to-cloud-api"
          or cloud_RoleName has "ca-ltc-api"
          or cloud_RoleName has "verification-functions"
          or cloud_RoleName has "func-ltc-verification"
      | where message == "verification.attempt.completed"
      | extend
          Outcome = tostring(customDimensions["verification.outcome"]),
          AttemptId = tostring(customDimensions["verification.attempt.id"])
      | where Outcome in ("server_error", "cancelled")
      | where isnotempty(AttemptId)
      | summarize ErrorCount = dcount(AttemptId) by bin(timestamp, 5m)
    QUERY
    time_aggregation_method = "Maximum"
    metric_measure_column   = "ErrorCount"
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

# Keep the existing Terraform address and Azure resource name to avoid an alert
# replacement gap; the operator-facing description uses the clearer wording.
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "verification_attempt_stuck" {
  name                = "alert-ltc-verification-attempt-stuck-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when verification is active beyond its allowed limit. Response guide: https://github.com/learntocloud/learn-to-cloud-app/blob/main/docs/runbooks/alerts.md#verification-active-beyond-limit"
  severity            = 2
  enabled             = true
  tags                = local.tags

  scopes                = [azurerm_application_insights.main.id]
  evaluation_frequency  = "PT5M"
  window_duration       = "PT15M"
  target_resource_types = ["microsoft.insights/components"]

  criteria {
    query                   = <<-QUERY
      traces
      | where cloud_RoleName in (
          "learn-to-cloud-verification-functions",
          "func-ltc-verification-${var.environment}"
        )
          or cloud_RoleName has "verification-functions"
          or cloud_RoleName has "func-ltc-verification"
      | where message == "verification.attempt.stuck"
      | extend
          AttemptId = tostring(customDimensions["verification.attempt.id"]),
          DurableStatus = tostring(customDimensions["durable_status"]),
          AttemptAgeSeconds = toint(customDimensions["attempt_age_seconds"]),
          StuckReason = tostring(customDimensions["stuck_reason"])
      | where isnotempty(AttemptId)
      | where StuckReason in (
          "active_beyond_limit",
          "status_query_failed",
          "status_recheck_failed"
        )
      | summarize arg_max(timestamp, DurableStatus, AttemptAgeSeconds) by AttemptId, StuckReason
      | project timestamp, AttemptId, DurableStatus, AttemptAgeSeconds, StuckReason
    QUERY
    time_aggregation_method = "Count"
    operator                = "GreaterThanOrEqual"
    threshold               = 1

    dimension {
      name     = "StuckReason"
      operator = "Include"
      values = [
        "active_beyond_limit",
        "status_query_failed",
        "status_recheck_failed",
      ]
    }

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  action {
    action_groups = [azurerm_monitor_action_group.critical.id]
  }
}

# Tier 3 follow-up from the #432 post-mortem: page if the production DB's
# applied Alembic head ever falls out of sync with the head baked into the
# deployed code (manual psql access, a half-applied migration, a future
# regression). /ready already compares the two on every poll and logs
# health.ready.schema_drift on mismatch without failing the probe itself, so
# this alert is the thing that actually pages a human; the readiness probe's
# 200/503 contract stays reserved for "can this pod serve traffic".
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "schema_drift" {
  name                = "alert-ltc-schema-drift-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when schema drift or the schema drift check persists for three evaluations. Response guide: https://github.com/learntocloud/learn-to-cloud-app/blob/main/docs/runbooks/alerts.md#schema-drift"
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
      | where cloud_RoleName in ("learn-to-cloud-api", "ca-ltc-api-${var.environment}")
          or cloud_RoleName has "learn-to-cloud-api"
          or cloud_RoleName has "ca-ltc-api"
      | where message in (
          "health.ready.schema_drift",
          "health.ready.schema_drift_check_failed"
        )
    QUERY
    time_aggregation_method = "Count"
    operator                = "GreaterThanOrEqual"
    threshold               = 1

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 3
      number_of_evaluation_periods             = 3
    }
  }

  action {
    action_groups = [azurerm_monitor_action_group.critical.id]
  }
}
