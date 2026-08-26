# State migration for the database migration job, moving it from
# azurerm_container_app_job to azapi without recreating the live resource. The
# removed block drops only the old Terraform address; the import adopts the
# existing ARM resource at its new address.
#
# Delete this file after the migration has been applied to every environment.
removed {
  from = azurerm_container_app_job.migrations

  lifecycle {
    destroy = false
  }
}

import {
  to = azapi_resource.migrations
  id = "${azurerm_resource_group.main.id}/providers/Microsoft.App/jobs/job-ltc-migrations-${var.environment}?api-version=${local.migration_job_api_version}"
}
