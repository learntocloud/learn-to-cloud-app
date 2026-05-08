resource "azapi_resource" "foundry_account" {
  type      = "Microsoft.CognitiveServices/accounts@2025-06-01"
  name      = local.foundry_account_name
  parent_id = azurerm_resource_group.main.id
  location  = var.foundry_location
  tags      = local.tags

  identity {
    type = "SystemAssigned"
  }

  body = {
    kind = "AIServices"
    properties = {
      allowProjectManagement        = true
      customSubDomainName           = local.foundry_account_name
      disableLocalAuth              = true
      dynamicThrottlingEnabled      = false
      publicNetworkAccess           = "Enabled"
      restrictOutboundNetworkAccess = false
    }
    sku = {
      name = "S0"
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "foundry_project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name      = local.foundry_project_name
  parent_id = azapi_resource.foundry_account.id
  location  = var.foundry_location
  tags      = local.tags

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {
      description = "Learn to Cloud verification grading project."
      displayName = "Learn to Cloud Verification ${var.environment}"
    }
  }

  schema_validation_enabled = false
}

resource "azapi_resource" "foundry_model_deployment" {
  type      = "Microsoft.CognitiveServices/accounts/deployments@2024-10-01"
  name      = var.foundry_model_deployment_name
  parent_id = azapi_resource.foundry_account.id
  tags      = local.tags

  body = {
    properties = {
      model = {
        format  = "OpenAI"
        name    = var.foundry_model_name
        version = var.foundry_model_version
      }
      versionUpgradeOption = "NoAutoUpgrade"
    }
    sku = {
      capacity = var.foundry_model_capacity
      name     = var.foundry_model_sku_name
    }
  }

  schema_validation_enabled = false
}
