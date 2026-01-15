# Monitoring Module: Action Groups, Metric Alerts, and Dashboard

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

# Action Group for alert notifications
resource "azurerm_monitor_action_group" "main" {
  name                = "ag-${var.app_name}-${var.environment}"
  resource_group_name = var.resource_group_name
  short_name          = "ltc-alerts"
  enabled             = true

  # Email receiver (conditional)
  dynamic "email_receiver" {
    for_each = var.alert_email_address != "" ? [1] : []
    content {
      name                    = "EmailAlert"
      email_address           = var.alert_email_address
      use_common_alert_schema = true
    }
  }

  # ARM role receiver for subscription owners
  arm_role_receiver {
    name                    = "SubscriptionOwners"
    role_id                 = "8e3af657-a8ff-443c-a75c-2fe8c4bcb635" # Owner role GUID
    use_common_alert_schema = true
  }

  tags = var.tags
}

# API Container App - High Error Rate Alert
resource "azurerm_monitor_metric_alert" "api_error_rate" {
  name                = "alert-${var.api_container_app_name}-error-rate"
  resource_group_name = var.resource_group_name
  scopes              = [var.api_container_app_id]
  description         = "Alert when API error rate exceeds 5%"
  severity            = 2
  enabled             = true
  auto_mitigate       = false

  frequency   = "PT5M"
  window_size = "PT15M"

  criteria {
    metric_namespace = "Microsoft.App/containerApps"
    metric_name      = "Requests"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 10

    dimension {
      name     = "statusCodeCategory"
      operator = "Include"
      values   = ["5xx"]
    }
  }

  action {
    action_group_id = azurerm_monitor_action_group.main.id
  }

  tags = var.tags
}

# API Container App - High Request Volume Alert
resource "azurerm_monitor_metric_alert" "api_requests" {
  name                = "alert-${var.api_container_app_name}-requests"
  resource_group_name = var.resource_group_name
  scopes              = [var.api_container_app_id]
  description         = "Alert when API receives unusually high request volume"
  severity            = 3
  enabled             = true
  auto_mitigate       = false

  frequency   = "PT5M"
  window_size = "PT15M"

  criteria {
    metric_namespace = "Microsoft.App/containerApps"
    metric_name      = "Requests"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 10000
  }

  action {
    action_group_id = azurerm_monitor_action_group.main.id
  }

  tags = var.tags
}

# API Container App - Restart Alert
resource "azurerm_monitor_metric_alert" "api_restarts" {
  name                = "alert-${var.api_container_app_name}-restarts"
  resource_group_name = var.resource_group_name
  scopes              = [var.api_container_app_id]
  description         = "Alert when API container restarts frequently"
  severity            = 2
  enabled             = true
  auto_mitigate       = false

  frequency   = "PT5M"
  window_size = "PT15M"

  criteria {
    metric_namespace = "Microsoft.App/containerApps"
    metric_name      = "RestartCount"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 3
  }

  action {
    action_group_id = azurerm_monitor_action_group.main.id
  }

  tags = var.tags
}

# Frontend Container App - High Error Rate Alert
resource "azurerm_monitor_metric_alert" "frontend_error_rate" {
  name                = "alert-${var.frontend_container_app_name}-error-rate"
  resource_group_name = var.resource_group_name
  scopes              = [var.frontend_container_app_id]
  description         = "Alert when Frontend error rate is high"
  severity            = 2
  enabled             = true
  auto_mitigate       = false

  frequency   = "PT5M"
  window_size = "PT15M"

  criteria {
    metric_namespace = "Microsoft.App/containerApps"
    metric_name      = "Requests"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 10

    dimension {
      name     = "statusCodeCategory"
      operator = "Include"
      values   = ["5xx"]
    }
  }

  action {
    action_group_id = azurerm_monitor_action_group.main.id
  }

  tags = var.tags
}

# PostgreSQL - High CPU Alert
resource "azurerm_monitor_metric_alert" "postgres_cpu" {
  name                = "alert-postgres-${var.environment}-cpu"
  resource_group_name = var.resource_group_name
  scopes              = [var.postgres_server_id]
  description         = "Alert when PostgreSQL CPU exceeds 80%"
  severity            = 2
  enabled             = true
  auto_mitigate       = false

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
    action_group_id = azurerm_monitor_action_group.main.id
  }

  tags = var.tags
}

# PostgreSQL - High Storage Alert
resource "azurerm_monitor_metric_alert" "postgres_storage" {
  name                = "alert-postgres-${var.environment}-storage"
  resource_group_name = var.resource_group_name
  scopes              = [var.postgres_server_id]
  description         = "Alert when PostgreSQL storage exceeds 80%"
  severity            = 2
  enabled             = true
  auto_mitigate       = false

  frequency   = "PT1H"
  window_size = "PT1H"

  criteria {
    metric_namespace = "Microsoft.DBforPostgreSQL/flexibleServers"
    metric_name      = "storage_percent"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 80
  }

  action {
    action_group_id = azurerm_monitor_action_group.main.id
  }

  tags = var.tags
}

# PostgreSQL - Connection Failures Alert
resource "azurerm_monitor_metric_alert" "postgres_connections" {
  name                = "alert-postgres-${var.environment}-connections"
  resource_group_name = var.resource_group_name
  scopes              = [var.postgres_server_id]
  description         = "Alert when PostgreSQL has connection failures"
  severity            = 2
  enabled             = true
  auto_mitigate       = false

  frequency   = "PT5M"
  window_size = "PT15M"

  criteria {
    metric_namespace = "Microsoft.DBforPostgreSQL/flexibleServers"
    metric_name      = "connections_failed"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 5
  }

  action {
    action_group_id = azurerm_monitor_action_group.main.id
  }

  tags = var.tags
}

# Application Insights - Failed Requests Alert
resource "azurerm_monitor_metric_alert" "appinsights_failed_requests" {
  name                = "alert-appinsights-${var.environment}-failed-requests"
  resource_group_name = var.resource_group_name
  scopes              = [var.app_insights_id]
  description         = "Alert when Application Insights detects failed requests"
  severity            = 2
  enabled             = true
  auto_mitigate       = false

  frequency   = "PT5M"
  window_size = "PT15M"

  criteria {
    metric_namespace = "microsoft.insights/components"
    metric_name      = "requests/failed"
    aggregation      = "Count"
    operator         = "GreaterThan"
    threshold        = 10
  }

  action {
    action_group_id = azurerm_monitor_action_group.main.id
  }

  tags = var.tags
}

# Application Insights - Exception Rate Alert
resource "azurerm_monitor_metric_alert" "appinsights_exceptions" {
  name                = "alert-appinsights-${var.environment}-exceptions"
  resource_group_name = var.resource_group_name
  scopes              = [var.app_insights_id]
  description         = "Alert when Application Insights detects high exception rate"
  severity            = 2
  enabled             = true
  auto_mitigate       = false

  frequency   = "PT5M"
  window_size = "PT15M"

  criteria {
    metric_namespace = "microsoft.insights/components"
    metric_name      = "exceptions/count"
    aggregation      = "Count"
    operator         = "GreaterThan"
    threshold        = 20
  }

  action {
    action_group_id = azurerm_monitor_action_group.main.id
  }

  tags = var.tags
}

# Note: Dashboard resource is complex and can be imported separately.
# The dashboard.bicep has extensive JSON configuration that can be managed
# manually or imported during migration. For simplicity, it's not included here
# but can be added using azurerm_portal_dashboard resource if needed.
