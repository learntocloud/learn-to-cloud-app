# Cache Module: Azure Cache for Redis
# Used for distributed rate limiting

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

# Azure Cache for Redis (conditional)
# Basic C0 tier is cost-effective for rate limiting (~$16/month)
resource "azurerm_redis_cache" "main" {
  count               = var.enable_redis ? 1 : 0
  name                = "redis-${var.app_name}-${var.environment}-${var.unique_suffix}"
  location            = var.location
  resource_group_name = var.resource_group_name

  sku_name = "Basic"
  family   = "C"
  capacity = 0 # C0 = 250MB, sufficient for rate limiting

  minimum_tls_version           = "1.2"
  public_network_access_enabled = true
  redis_version                 = "6"
  non_ssl_port_enabled          = false

  tags = var.tags
}
