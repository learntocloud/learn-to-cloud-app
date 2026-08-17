# Modelled with azapi rather than azurerm_container_app_job because the
# AzureRM provider calls Microsoft.App/jobs/listSecrets/action on every refresh,
# even though this job has no secrets. A normal ARM GET is sufficient for this
# resource and keeps the PR planning identity strictly read-only.
locals {
  migration_job_resource_type = "Microsoft.App/jobs@2024-03-01"
  migration_job_configuration = {
    triggerType       = "Manual"
    replicaTimeout    = 1800
    replicaRetryLimit = 0
    manualTriggerConfig = {
      parallelism            = 1
      replicaCompletionCount = 1
    }
    registries = [
      {
        server   = azurerm_container_registry.main.login_server
        identity = azurerm_user_assigned_identity.migrations.id
      },
    ]
  }
}

resource "azapi_resource" "migrations" {
  type      = local.migration_job_resource_type
  name      = "job-ltc-migrations-${var.environment}"
  parent_id = azurerm_resource_group.main.id
  location  = azurerm_resource_group.main.location
  tags      = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.migrations.id]
  }

  body = {
    properties = {
      environmentId = azurerm_container_app_environment.main.id

      configuration = local.migration_job_configuration

      template = {
        containers = [
          {
            name    = "migrations"
            image   = "${azurerm_container_registry.main.login_server}/migrations:latest"
            command = ["python"]
            args    = ["scripts/run_migrations.py"]
            resources = {
              cpu    = 0.5
              memory = "1Gi"
            }
            env = [
              {
                name  = "DATABASE__HOST"
                value = azurerm_postgresql_flexible_server.main.fqdn
              },
              {
                name  = "DATABASE__USER"
                value = local.migration_postgres_role
              },
              {
                name  = "DATABASE__NAME"
                value = azurerm_postgresql_flexible_server_database.main.name
              },
              {
                name  = "AZURE_CLIENT_ID"
                value = azurerm_user_assigned_identity.migrations.client_id
              },
              {
                name  = "POSTGRES_VERIFICATION_FUNCTIONS_ROLE"
                value = local.verification_functions_postgres_role
              },
            ]
          },
        ]
      }
    }
  }

  lifecycle {
    # Deploy updates the image to the immutable commit tag after Terraform has
    # run. Infrastructure plans must preserve that independently managed tag.
    ignore_changes = [body.properties.template.containers[0].image]
  }

  depends_on = [
    azurerm_role_assignment.migrations_acr_pull,
    azurerm_postgresql_flexible_server_database.main,
  ]
}
