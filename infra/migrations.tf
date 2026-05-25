resource "azurerm_container_app_job" "migrations" {
  name                         = "job-ltc-migrations-${var.environment}"
  location                     = azurerm_resource_group.main.location
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  replica_timeout_in_seconds   = 1800
  replica_retry_limit          = 0
  tags                         = local.tags

  lifecycle {
    ignore_changes = [
      template[0].container[0].image,
    ]
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.migrations.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.migrations.id
  }

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  template {
    container {
      name    = "migrations"
      image   = "${azurerm_container_registry.main.login_server}/migrations:bootstrap"
      command = ["python"]
      args    = ["scripts/run_migrations.py"]
      cpu     = 0.5
      memory  = "1Gi"

      env {
        name  = "DATABASE__HOST"
        value = azurerm_postgresql_flexible_server.main.fqdn
      }

      env {
        name  = "DATABASE__USER"
        value = local.migration_postgres_role
      }

      env {
        name  = "DATABASE__NAME"
        value = azurerm_postgresql_flexible_server_database.main.name
      }

      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.migrations.client_id
      }

      env {
        name  = "POSTGRES_VERIFICATION_FUNCTIONS_ROLE"
        value = local.verification_functions_postgres_role
      }

      env {
        name  = "CONTENT__DIR"
        value = "/app/content/phases"
      }
    }
  }

  depends_on = [
    azurerm_role_assignment.migrations_acr_pull,
    azurerm_postgresql_flexible_server_database.main,
  ]
}
