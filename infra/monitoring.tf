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
  description         = "Detects an API telemetry setup failure recorded by the app's canonical startup log. Response guide: https://github.com/learntocloud/learn-to-cloud-app/blob/main/docs/runbooks/alerts.md#telemetry-pipeline-failure"
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
      | where tostring(ParsedLog.event) == "telemetry.configure.failed"
      | summarize ConfigureFailureCount = count()
      | where ConfigureFailureCount >= 1
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

# LLM grading emits only a fixed safe category in the application log. The alert
# query deliberately excludes attempt, learner, provider-request, and error-detail
# fields so the common alert payload is safe to deliver to the action group.
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "verification_llm_immediate_failure" {
  name                = "alert-ltc-verification-llm-immediate-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert immediately for non-retryable LLM grading failures. Query: https://portal.azure.com/#view/Microsoft_Azure_Monitoring_Logs/LogsBlade. Response guide: https://github.com/learntocloud/learn-to-cloud-app/blob/main/docs/runbooks/alerts.md#verification-llm-grading-failures"
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
      | where message == "verification.llm_grading.failed"
      | extend ErrorType = tostring(customDimensions["error.type"])
      | where ErrorType in ("llm.configuration", "llm.authentication", "llm.authorization", "llm.response_validation", "llm.unknown")
      | summarize FailureCount = count() by ErrorType, bin(timestamp, 5m)
    QUERY
    time_aggregation_method = "Maximum"
    metric_measure_column   = "FailureCount"
    operator                = "GreaterThanOrEqual"
    threshold               = 1

    dimension {
      name     = "ErrorType"
      operator = "Include"
      values   = ["llm.configuration", "llm.authentication", "llm.authorization", "llm.response_validation", "llm.unknown"]
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

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "verification_llm_transient_failure" {
  name                = "alert-ltc-verification-llm-transient-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert after three exhausted same-category transient LLM grading failures in 15 minutes. Query: https://portal.azure.com/#view/Microsoft_Azure_Monitoring_Logs/LogsBlade. Response guide: https://github.com/learntocloud/learn-to-cloud-app/blob/main/docs/runbooks/alerts.md#verification-llm-grading-failures"
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
      | where message == "verification.llm_grading.failed"
      | extend ErrorType = tostring(customDimensions["error.type"])
      | where ErrorType in ("llm.rate_limit", "llm.provider_unavailable", "llm.network", "llm.timeout")
      | summarize FailureCount = count() by ErrorType
    QUERY
    time_aggregation_method = "Maximum"
    metric_measure_column   = "FailureCount"
    operator                = "GreaterThanOrEqual"
    threshold               = 3

    dimension {
      name     = "ErrorType"
      operator = "Include"
      values   = ["llm.rate_limit", "llm.provider_unavailable", "llm.network", "llm.timeout"]
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
          DurableStatus = tostring(customDimensions["verification.durable.status"]),
          AttemptAgeSeconds = toint(customDimensions["verification.attempt.age_seconds"]),
          StuckReason = tostring(customDimensions["verification.stuck.reason"])
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
