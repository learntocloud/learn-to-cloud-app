# -----------------------------------------------------------------------------
# Azure OpenAI — model deployment for AI-powered code analysis
# The Agent Framework calls this endpoint directly via AzureOpenAIChatClient.
# -----------------------------------------------------------------------------

# One-time import: gpt-5-mini deployment was created outside Terraform.
# Remove this block after the first successful apply.
import {
  to = azurerm_cognitive_deployment.llm
  id = "/subscriptions/96e40cb1-d5eb-46c6-b0fd-8e64eb9c119d/resourceGroups/rg-ltc-dev/providers/Microsoft.CognitiveServices/accounts/oai-ltc-dev-8v4tyz/deployments/gpt-5-mini"
}

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
