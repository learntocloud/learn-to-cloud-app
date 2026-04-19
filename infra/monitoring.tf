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
    "us-va-ash-azr",   # East US
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
