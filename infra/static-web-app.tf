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
