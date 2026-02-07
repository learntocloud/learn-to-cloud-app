# -----------------------------------------------------------------------------
# Azure OpenAI — model deployment for AI-powered code analysis
# The Copilot SDK (BYOK mode) sends requests here via the CLI sidecar.
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
