resource "azuread_application" "verification_functions" {
  display_name     = local.verification_functions_auth_app_name
  identifier_uris  = [local.verification_functions_auth_audience]
  sign_in_audience = "AzureADMyOrg"

  api {
    requested_access_token_version = 2
  }
}

resource "azuread_service_principal" "verification_functions" {
  client_id = azuread_application.verification_functions.client_id
}
