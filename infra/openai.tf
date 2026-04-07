# -----------------------------------------------------------------------------
# Azure OpenAI — model deployment for AI-powered code analysis
# The Agent Framework calls this endpoint via OpenAIChatClient + managed identity.
# -----------------------------------------------------------------------------

resource "azurerm_cognitive_account" "openai" {
  name                  = "oai-ltc-${var.environment}-${local.suffix}"
  resource_group_name   = azurerm_resource_group.main.name
  location              = var.location
  kind                  = "OpenAI"
  sku_name              = "S0"
  custom_subdomain_name = "oai-ltc-${var.environment}-${local.suffix}"
  tags                  = local.tags
}

resource "azurerm_cognitive_deployment" "llm" {
  name                 = var.llm_model
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = var.llm_model
    version = var.llm_model_version
  }

  sku {
    name     = "GlobalStandard"
    capacity = var.llm_capacity
  }
}

resource "azurerm_role_assignment" "api_openai_user" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_user_assigned_identity.api.principal_id
}
