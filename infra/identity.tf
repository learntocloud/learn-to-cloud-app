data "azurerm_client_config" "current" {}

resource "azurerm_user_assigned_identity" "api" {
  name                = "id-ltc-api-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.tags
}
