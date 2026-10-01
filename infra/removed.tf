# Azure does not support DELETE on a site's authsettingsV2 config (HTTP 405).
# Forget it instead; it is deleted with the retired Function App.
removed {
  from = azapi_resource.verification_functions_auth

  lifecycle {
    destroy = false
  }
}
