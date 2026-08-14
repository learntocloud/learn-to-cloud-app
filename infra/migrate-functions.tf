# State migration for the verification Function App, moving it from
# azurerm_function_app_flex_consumption to azapi without recreating the live
# app. The removed block drops the old address from state only; the import
# blocks adopt the existing site and its auth configuration.
#
# Delete this file once the migration has been applied to every environment.
removed {
  from = azurerm_function_app_flex_consumption.verification

  lifecycle {
    destroy = false
  }
}

import {
  to = azapi_resource.verification_functions
  id = "${azurerm_resource_group.main.id}/providers/Microsoft.Web/sites/func-ltc-verification-${var.environment}"
}

import {
  to = azapi_resource.verification_functions_auth
  id = "${azurerm_resource_group.main.id}/providers/Microsoft.Web/sites/func-ltc-verification-${var.environment}/config/authsettingsV2"
}
