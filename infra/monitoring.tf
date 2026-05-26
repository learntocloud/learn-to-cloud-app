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

# The API-wide alert above catches fast 5xx storms. This route-specific alert
# catches slow leaks on the user-facing verification submit path, where even a
# few failures can silently block progress.
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "api_verification_submit_5xx_leak" {
  name                = "alert-ltc-api-verification-submit-5xx-leak-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when verification submits return 2+ 5xx errors in 24 hours"
  severity            = 2
  enabled             = true
  tags                = local.tags

  scopes                = [azurerm_application_insights.main.id]
  evaluation_frequency  = "PT1H"
  window_duration       = "P1D"
  target_resource_types = ["microsoft.insights/components"]

  criteria {
    query                   = <<-QUERY
      requests
      | where cloud_RoleName in ("learn-to-cloud-api", "ca-ltc-api-${var.environment}")
          or cloud_RoleName has "learn-to-cloud-api"
          or cloud_RoleName has "ca-ltc-api"
      | where resultCode startswith "5"
      | where name has "/htmx/github/submit"
          or url has "/htmx/github/submit"
      | summarize ErrorCount = count()
    QUERY
    time_aggregation_method = "Maximum"
    metric_measure_column   = "ErrorCount"
    operator                = "GreaterThanOrEqual"
    threshold               = 2

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
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
  description         = "Alert when verification Functions record non-learner API exceptions in a 5-minute window"
  severity            = 1
  enabled             = true
  tags                = local.tags

  scopes                = [azurerm_application_insights.main.id]
  evaluation_frequency  = "PT5M"
  window_duration       = "PT5M"
  target_resource_types = ["microsoft.insights/components"]

  criteria {
    query                   = <<-QUERY
      let LearnerApiDependencyFailures =
          dependencies
          | where cloud_RoleName in ("learn-to-cloud-verification-functions", "func-ltc-verification-${var.environment}")
              or cloud_RoleName has "verification-functions"
              or cloud_RoleName has "func-ltc-verification"
          | where type == "HTTP"
          | where name in ("POST /entries", "GET /entries")
              or name startswith "DELETE /entries/"
          | project operation_Id, dependencySpanId = id;
      exceptions
      | where cloud_RoleName in ("learn-to-cloud-verification-functions", "func-ltc-verification-${var.environment}")
          or cloud_RoleName has "verification-functions"
          or cloud_RoleName has "func-ltc-verification"
      | join kind=leftanti LearnerApiDependencyFailures
          on operation_Id, $left.operation_ParentId == $right.dependencySpanId
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

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "verification_durable_errors" {
  name                = "alert-ltc-verification-durable-errors-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when Durable verification logs warning or error traces in a 5-minute window"
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
      | extend Category = tostring(customDimensions.Category)
      | where cloud_RoleName in ("learn-to-cloud-verification-functions", "func-ltc-verification-${var.environment}")
          or cloud_RoleName has "verification-functions"
          or cloud_RoleName has "func-ltc-verification"
      | where severityLevel >= 3
      | where Category has "DurableTask"
          or message has "DurableTask"
          or message has "orchestration"
          or message has "activity"
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
