# Cache Module Outputs

output "redis_cache_id" {
  description = "ID of the Redis cache (if enabled)"
  value       = var.enable_redis ? azurerm_redis_cache.main[0].id : null
}

output "redis_cache_name" {
  description = "Name of the Redis cache (if enabled)"
  value       = var.enable_redis ? azurerm_redis_cache.main[0].name : null
}

output "redis_hostname" {
  description = "Hostname of the Redis cache (if enabled)"
  value       = var.enable_redis ? azurerm_redis_cache.main[0].hostname : null
}

output "redis_ssl_port" {
  description = "SSL port of the Redis cache (if enabled)"
  value       = var.enable_redis ? azurerm_redis_cache.main[0].ssl_port : null
}

output "redis_primary_key" {
  description = "Primary key for Redis cache (if enabled)"
  value       = var.enable_redis ? azurerm_redis_cache.main[0].primary_access_key : null
  sensitive   = true
}

output "redis_connection_string" {
  description = "Connection string for Redis cache in format: rediss://:password@hostname:port/0 (if enabled)"
  value       = var.enable_redis ? "rediss://:${azurerm_redis_cache.main[0].primary_access_key}@${azurerm_redis_cache.main[0].hostname}:${azurerm_redis_cache.main[0].ssl_port}/0" : null
  sensitive   = true
}
