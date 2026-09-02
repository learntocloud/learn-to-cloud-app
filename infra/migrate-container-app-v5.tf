# AzureRM v5 removed a computed probe field without a state upgrader.
# Re-adopt the live Container App at a clean address without recreating it.
removed {
  from = azurerm_container_app.api

  lifecycle {
    destroy = false
  }
}

import {
  to = azurerm_container_app.api_v5
  id = "${azurerm_resource_group.main.id}/providers/Microsoft.App/containerApps/ca-ltc-api-${var.environment}"
}
