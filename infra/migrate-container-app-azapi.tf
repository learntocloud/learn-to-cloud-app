# Move the existing API Container App from AzureRM to AzAPI without recreating
# the live resource. AzureRM calls listSecrets during every refresh; AzAPI uses
# the normal ARM GET required by the read-only PR planning identity.
#
# Delete this file after the migration has been applied to every environment.
removed {
  from = azurerm_container_app.api_v5

  lifecycle {
    destroy = false
  }
}

import {
  to = azapi_resource.api
  id = "${azurerm_resource_group.main.id}/providers/Microsoft.App/containerApps/ca-ltc-api-${var.environment}?api-version=${local.api_container_app_api_version}"
}
