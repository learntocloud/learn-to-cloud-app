terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  backend "azurerm" {
    resource_group_name  = "rg-terraform-state"
    storage_account_name = "stterraformstateb1ac9ddc"
    container_name       = "tfstate"
    key                  = "learn-to-cloud-dev.tfstate"
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = true
    }
  }
  subscription_id = var.subscription_id
}

provider "azapi" {}

# -----------------------------------------------------------------------------
# Random suffix for unique names
# -----------------------------------------------------------------------------
resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false

  lifecycle {
    ignore_changes = all
  }
}

locals {
  suffix              = random_string.suffix.result
  resource_group_name = "rg-ltc-${var.environment}"
  tags = {
    environment = var.environment
    project     = "learntocloud"
    managed_by  = "terraform"
  }
}

# -----------------------------------------------------------------------------
# Resource Group
# -----------------------------------------------------------------------------
resource "azurerm_resource_group" "main" {
  name     = local.resource_group_name
  location = var.location
  tags     = local.tags
}

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
# Container Registry
# -----------------------------------------------------------------------------
resource "azurerm_container_registry" "main" {
  name                = "crltc${local.suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = true
  tags                = local.tags
}

# -----------------------------------------------------------------------------
# PostgreSQL Flexible Server
# -----------------------------------------------------------------------------
resource "azurerm_postgresql_flexible_server" "main" {
  name                          = "psql-ltc-${var.environment}-${local.suffix}"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  version                       = "16"
  storage_mb                    = 32768
  sku_name                      = "B_Standard_B1ms"
  backup_retention_days         = 7
  geo_redundant_backup_enabled  = false
  public_network_access_enabled = true
  zone                          = "3"
  tags                          = local.tags

  authentication {
    active_directory_auth_enabled = true
    password_auth_enabled         = false
  }
}

resource "azurerm_postgresql_flexible_server_database" "main" {
  name      = "learntocloud"
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "allow_azure" {
  name             = "AllowAzureServices"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# -----------------------------------------------------------------------------
# Managed Identity for API
# -----------------------------------------------------------------------------
resource "azurerm_user_assigned_identity" "api" {
  name                = "id-ltc-api-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.tags
}

# -----------------------------------------------------------------------------
# PostgreSQL Entra Admin (Managed Identity)
# -----------------------------------------------------------------------------
data "azurerm_client_config" "current" {}

resource "azurerm_postgresql_flexible_server_active_directory_administrator" "api" {
  server_name         = azurerm_postgresql_flexible_server.main.name
  resource_group_name = azurerm_resource_group.main.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  object_id           = azurerm_user_assigned_identity.api.principal_id
  principal_name      = azurerm_user_assigned_identity.api.name
  principal_type      = "ServicePrincipal"
}

# -----------------------------------------------------------------------------
# Container Apps Environment
# -----------------------------------------------------------------------------
resource "azurerm_container_app_environment" "main" {
  name                       = "cae-ltc-${var.environment}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.tags
}

# -----------------------------------------------------------------------------
# API Container App
# -----------------------------------------------------------------------------
resource "azurerm_container_app" "api" {
  name                         = "ca-ltc-api-${var.environment}"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.api.id]
  }

  registry {
    server               = azurerm_container_registry.main.login_server
    username             = azurerm_container_registry.main.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.main.admin_password
  }

  secret {
    name  = "clerk-secret-key"
    value = var.clerk_secret_key
  }

  secret {
    name  = "clerk-webhook-secret"
    value = var.clerk_webhook_signing_secret
  }

  secret {
    name  = "google-api-key"
    value = var.google_api_key
  }

  secret {
    name  = "ctf-master-secret"
    value = var.ctf_master_secret
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "http"

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = 1
    max_replicas = 3

    container {
      name   = "api"
      image  = "${azurerm_container_registry.main.login_server}/api:v2"
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "POSTGRES_HOST"
        value = azurerm_postgresql_flexible_server.main.fqdn
      }

      env {
        name  = "POSTGRES_USER"
        value = azurerm_user_assigned_identity.api.name
      }

      env {
        name  = "POSTGRES_DATABASE"
        value = azurerm_postgresql_flexible_server_database.main.name
      }

      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.api.client_id
      }

      env {
        name  = "CLERK_PUBLISHABLE_KEY"
        value = var.clerk_publishable_key
      }

      env {
        name        = "CLERK_SECRET_KEY"
        secret_name = "clerk-secret-key"
      }

      env {
        name        = "CLERK_WEBHOOK_SIGNING_SECRET"
        secret_name = "clerk-webhook-secret"
      }

      env {
        name        = "GOOGLE_API_KEY"
        secret_name = "google-api-key"
      }

      env {
        name        = "CTF_MASTER_SECRET"
        secret_name = "ctf-master-secret"
      }

      env {
        name  = "SYNC_GRADING_CONCEPTS_ON_STARTUP"
        value = "true"
      }

      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.main.connection_string
      }

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }

      env {
        name  = "FRONTEND_URL"
        value = var.frontend_custom_domain != "" ? "https://${var.frontend_custom_domain}" : "https://ca-ltc-frontend-${var.environment}.${azurerm_container_app_environment.main.default_domain}"
      }

      liveness_probe {
        transport = "HTTP"
        path      = "/health"
        port      = 8000
        initial_delay            = 30
        interval_seconds         = 30
        timeout                  = 5
        failure_count_threshold  = 3
      }

      readiness_probe {
        transport = "HTTP"
        path      = "/health"
        port      = 8000
        interval_seconds         = 10
        timeout                  = 5
        failure_count_threshold  = 3
      }

      startup_probe {
        transport = "HTTP"
        path      = "/health"
        port      = 8000
        interval_seconds         = 10
        timeout                  = 5
        failure_count_threshold  = 30
      }
    }
  }

  depends_on = [azurerm_postgresql_flexible_server_database.main]
}

# -----------------------------------------------------------------------------
# Frontend Static Web App
# -----------------------------------------------------------------------------
# Azure Static Web Apps provides global CDN, automatic HTTPS, and instant deploys.
# Standard tier required for Container Apps backend linking.

resource "azurerm_static_web_app" "frontend" {
  name                = "swa-ltc-frontend-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku_tier            = "Standard"
  sku_size            = "Standard"
  tags                = local.tags
}

# Link the API Container App as the backend for /api/* routes
# Uses AzAPI because azurerm doesn't support Container Apps linking yet
resource "azapi_resource" "swa_backend_link" {
  type      = "Microsoft.Web/staticSites/linkedBackends@2023-01-01"
  name      = "api"
  parent_id = azurerm_static_web_app.frontend.id

  body = {
    properties = {
      backendResourceId = azurerm_container_app.api.id
      region            = azurerm_resource_group.main.location
    }
  }

  depends_on = [
    azurerm_static_web_app.frontend,
    azurerm_container_app.api
  ]
}

# -----------------------------------------------------------------------------
# Custom Domain for Frontend (app.learntocloud.guide)
# -----------------------------------------------------------------------------
# Prerequisites: DNS records must be configured BEFORE applying:
#   - CNAME: app → <swa_default_host_name>
#   - TXT: Validation handled automatically by SWA
#
# NOTE: The custom domain was imported into state with:
#   terraform import 'azurerm_static_web_app_custom_domain.frontend[0]' \
#     "/subscriptions/96e40cb1-d5eb-46c6-b0fd-8e64eb9c119d/resourceGroups/rg-ltc-dev/providers/Microsoft.Web/staticSites/swa-ltc-frontend-dev/customDomains/app.learntocloud.guide"

resource "azurerm_static_web_app_custom_domain" "frontend" {
  count             = var.frontend_custom_domain != "" ? 1 : 0
  static_web_app_id = azurerm_static_web_app.frontend.id
  domain_name       = var.frontend_custom_domain
  validation_type   = "cname-delegation"
}

output "swa_default_hostname" {
  description = "Static Web App default hostname for DNS CNAME record"
  value       = azurerm_static_web_app.frontend.default_host_name
}

output "swa_api_key" {
  description = "Static Web App deployment token (for CI/CD)"
  value       = azurerm_static_web_app.frontend.api_key
  sensitive   = true
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

# Action Group for Warning alerts (Sev2) - email only, no paging
# For Slack integration, add webhook_receiver with var.slack_webhook_url
resource "azurerm_monitor_action_group" "warning" {
  name                = "ag-ltc-warning-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "ltcwarn"
  tags                = local.tags

  email_receiver {
    name                    = "team"
    email_address           = var.alert_email
    use_common_alert_schema = true
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
    action_groups = [azurerm_monitor_action_group.warning.id]
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
# Monitoring - Circuit Breaker Alerts
# -----------------------------------------------------------------------------
# These alerts monitor the Clerk auth circuit breaker for infrastructure issues.
# Circuit breaker opens when JWKS fetching fails repeatedly (Clerk outage).

# Alert: Circuit Breaker Open > 5 min (Sev2 - Warning)
# Fires when circuit_breaker_open_total metric indicates circuit has been opening
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "circuit_breaker_open_warning" {
  name                = "alert-ltc-circuit-open-warning-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when Clerk auth circuit breaker is open (5+ min of failures)"
  severity            = 2
  enabled             = true
  tags                = local.tags

  scopes                = [azurerm_application_insights.main.id]
  evaluation_frequency  = "PT5M"
  window_duration       = "PT5M"
  target_resource_types = ["microsoft.insights/components"]

  criteria {
    query = <<-QUERY
      customMetrics
      | where name == "circuit_breaker_open_total"
      | where customDimensions.circuit == "clerk_auth"
      | summarize OpenCount = sum(value) by bin(timestamp, 5m)
      | where OpenCount > 0
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
    action_groups = [azurerm_monitor_action_group.warning.id]
  }
}

# Alert: Circuit Breaker Open > 15 min (Sev1 - Critical)
# Extended outage - pages on-call
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "circuit_breaker_open_critical" {
  name                = "alert-ltc-circuit-open-critical-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when Clerk auth circuit breaker is open for extended period (15+ min)"
  severity            = 1
  enabled             = true
  tags                = local.tags

  scopes                = [azurerm_application_insights.main.id]
  evaluation_frequency  = "PT5M"
  window_duration       = "PT15M"
  target_resource_types = ["microsoft.insights/components"]

  criteria {
    query = <<-QUERY
      customMetrics
      | where name == "circuit_breaker_open_total"
      | where customDimensions.circuit == "clerk_auth"
      | summarize OpenCount = sum(value) by bin(timestamp, 15m)
      | where OpenCount > 0
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

# Alert: Circuit Breaker Flapping (Sev1 - Critical)
# Multiple state transitions indicate instability - pages on-call
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "circuit_breaker_flapping" {
  name                = "alert-ltc-circuit-flapping-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  description         = "Alert when circuit breaker is flapping (>5 state changes in 10 min)"
  severity            = 1
  enabled             = true
  tags                = local.tags

  scopes                = [azurerm_application_insights.main.id]
  evaluation_frequency  = "PT5M"
  window_duration       = "PT10M"
  target_resource_types = ["microsoft.insights/components"]

  criteria {
    query = <<-QUERY
      customMetrics
      | where name == "circuit_breaker_state_change"
      | where customDimensions.circuit == "clerk_auth"
      | summarize StateChanges = sum(value) by bin(timestamp, 10m)
      | where StateChanges > 5
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
