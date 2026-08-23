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

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "verification_functions_5xx_errors" {
  name                = "alert-ltc-verification-functions-5xx-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when verification Functions return any 5xx errors in a 5-minute window"
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
      | where cloud_RoleName in ("learn-to-cloud-verification-functions", "func-ltc-verification-${var.environment}")
          or cloud_RoleName has "verification-functions"
          or cloud_RoleName has "func-ltc-verification"
      | where resultCode startswith "5"
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

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "verification_functions_exceptions" {
  name                = "alert-ltc-verification-functions-exceptions-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when a non-HTTP verification Functions invocation remains failed after a 5-minute correlation delay"
  severity            = 1
  enabled             = true
  tags                = local.tags

  scopes                = [azurerm_application_insights.main.id]
  evaluation_frequency  = "PT5M"
  window_duration       = "PT15M"
  target_resource_types = ["microsoft.insights/components"]

  criteria {
    query                   = <<-QUERY
      let TerminalVerificationAttempts =
          traces
          | where timestamp > ago(15m)
          | where cloud_RoleName in ("learn-to-cloud-verification-functions", "func-ltc-verification-${var.environment}")
              or cloud_RoleName has "verification-functions"
              or cloud_RoleName has "func-ltc-verification"
          | where message in ("verification.attempt.finalized", "verification.attempt.terminalized")
          | project operation_Id;
      let FunctionsHttp5xx =
          requests
          | where timestamp > ago(15m)
          | where cloud_RoleName in ("learn-to-cloud-verification-functions", "func-ltc-verification-${var.environment}")
              or cloud_RoleName has "verification-functions"
              or cloud_RoleName has "func-ltc-verification"
          | where resultCode startswith "5"
          | project operation_Id;
      exceptions
      | where cloud_RoleName in ("learn-to-cloud-verification-functions", "func-ltc-verification-${var.environment}")
          or cloud_RoleName has "verification-functions"
          or cloud_RoleName has "func-ltc-verification"
      | where isnotempty(operation_Id)
      | where timestamp between (ago(15m) .. ago(5m))
      | join kind=leftanti TerminalVerificationAttempts on operation_Id
      | join kind=leftanti FunctionsHttp5xx on operation_Id
      | summarize ExceptionRows = count() by operation_Id
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

# Learner-facing verification system failures cross two telemetry boundaries:
# the API records a handled start failure before Functions can claim an attempt,
# while Functions records an authoritative server_error after an attempt starts.
# Both mean our system, not the learner's validation, prevented completion.
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "verification_system_error" {
  name                = "alert-ltc-verification-system-error-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert on any handled Durable start failure or terminal verification server_error"
  severity            = 2
  enabled             = true
  tags                = local.tags

  scopes                = [azurerm_application_insights.main.id]
  evaluation_frequency  = "PT5M"
  window_duration       = "PT5M"
  target_resource_types = ["microsoft.insights/components"]

  criteria {
    query                   = <<-QUERY
      let DurableStartFailures =
          traces
          | where timestamp > ago(5m)
          | extend ErrorType = tostring(customDimensions.error_type)
          | where cloud_RoleName in ("learn-to-cloud-api", "ca-ltc-api-${var.environment}")
              or cloud_RoleName has "learn-to-cloud-api"
              or cloud_RoleName has "ca-ltc-api"
          | where message == "htmx.submit.durable_start_failed"
          | where ErrorType == "DurableVerificationStartError"
          | project FailureKey = strcat("start:", operation_Id);
      let TerminalServerErrors =
          traces
          | where timestamp > ago(5m)
          | extend
              Outcome = tostring(customDimensions.outcome),
              AttemptId = tostring(customDimensions.attempt_id)
          | where cloud_RoleName in ("learn-to-cloud-verification-functions", "func-ltc-verification-${var.environment}")
              or cloud_RoleName has "verification-functions"
              or cloud_RoleName has "func-ltc-verification"
          | where message in ("verification.attempt.finalized", "verification.attempt.terminalized")
          | where Outcome == "server_error"
          | where isnotempty(AttemptId)
          | project FailureKey = strcat("attempt:", AttemptId);
      union DurableStartFailures, TerminalServerErrors
      | summarize ErrorCount = dcount(FailureKey)
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

# Additive replacement for verification_system_error during the telemetry
# migration. It evaluates in shadow mode without an action group until cutover,
# and only uses canonical events emitted after PostgreSQL accepts the first
# terminal result for an attempt.
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "verification_attempt_system_error" {
  name                = "alert-ltc-verification-attempt-system-error-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when a saved verification attempt outcome is server_error"
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
      | where Outcome == "server_error"
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

}

# The reconciler emits this event only after a final database read confirms the
# attempt is still active beyond its allowed duration. It also starts in shadow
# mode so deploying it cannot duplicate the existing verification pages.
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "verification_attempt_stuck" {
  name                = "alert-ltc-verification-attempt-stuck-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when a verification attempt remains active beyond its maximum duration"
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
      | extend AttemptId = tostring(customDimensions["verification.attempt.id"])
      | where isnotempty(AttemptId)
      | summarize StuckCount = dcount(AttemptId) by bin(timestamp, 5m)
    QUERY
    time_aggregation_method = "Maximum"
    metric_measure_column   = "StuckCount"
    operator                = "GreaterThanOrEqual"
    threshold               = 1

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
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
  description         = "Alert when the deployed DB's Alembic head diverges from the deployed code's Alembic head for more than 10 minutes"
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
      | where cloud_RoleName in ("learn-to-cloud-api", "ca-ltc-api-${var.environment}")
          or cloud_RoleName has "learn-to-cloud-api"
          or cloud_RoleName has "ca-ltc-api"
      | where message has "health.ready.schema_drift"
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
