# Terraform cleanup backlog

Outstanding findings for the current API-container deployment. Recheck each
item against the deployed state before implementing it.

## Security and networking

- [ ] **PostgreSQL is reachable from all of Azure.** `database.tf` combines
      public network access with an `AllowAzureServices` (`0.0.0.0`) firewall
      rule. Entra-only authentication remains the access control. Restricting
      network access requires a networking decision for Container Apps:
      VNet integration, stable outbound addresses, or private networking.
- [ ] **Key Vault has no network restrictions.** Restrict public access after
      choosing how the API and migration job will reach it.

## Structure

- [ ] **Separate concerns in `provider.tf`.** Consider splitting version
      constraints, provider configuration, resources, and locals into dedicated
      files.
- [ ] **Review repeated alert configuration.** `monitoring.tf` has several
      similar scheduled-query rules. Share configuration only where it improves
      clarity; preserve each alert's query, dimensions, thresholds, and address.
- [ ] **Reduce null-default indirection.** Put stable defaults on variables
      rather than resolving them through `coalesce()` in locals. Keep
      environment-dependent defaults explicit.

## Consistency

- [ ] **Choose a naming rule for `local.suffix`.** Key Vault, PostgreSQL, ACR,
      Log Analytics, Application Insights, and Foundry use it; several
      application and supporting resources do not.
- [ ] **Normalize output naming.** Uppercase workflow outputs and snake_case
      outputs coexist, and some database outputs overlap. Coordinate changes
      with every workflow consumer.
- [ ] **Review disabled azapi schema validation.** Enable validation for stable
      resource schemas where supported; the migration job already uses it.
- [ ] **Consolidate duplicated site URLs.** `https://learntocloud.guide` appears
      in both API CORS configuration and the availability web test.
- [ ] **Narrow `ignore_changes = all` on `random_string.suffix`.** Retain the
      existing value without unnecessarily ignoring every property.
- [ ] **Review redundant database dependencies.** Keep explicit role-assignment
      ordering, but remove dependencies already expressed through resource
      references when safe.
- [ ] **Keep infrastructure validation aligned across local and CI workflows.**
      Preserve formatting, validation, and mocked-plan coverage as resources
      change; do not assume the Python-only checks cover Terraform.

## Completed work

- [x] Removed the separate verification host, scheduler, storage, identities,
      role assignments, and storage diagnostics. Verification now runs inside
      the API, so their old networking and storage-authentication TODOs no
      longer apply. Earlier identity-based storage and explicit Key Vault
      reference fixes are historical, not remaining deployment requirements.
- [x] Moved runtime secrets out of inline Terraform values to Key Vault
      references, including the former smoke-test token.
- [x] Added diagnostic settings for Key Vault, the container registry, and
      PostgreSQL using explicit categories.
- [x] Pinned Terraform's supported version range and set the azapi subscription
      explicitly.
- [x] Migrated the Container Apps migration job to azapi so refresh does not
      call `Microsoft.App/jobs/listSecrets/action`, preserving its identity and
      rollout boundary. Temporary state-migration declarations were removed
      after deployment.
- [x] Completed the AzureRM 5 migration from #802. The API uses
      `azurerm_container_app.api_v5`; its temporary migration declarations were
      removed after deployment.

Issues #743 and #741 are closed. Their completed secretless-infrastructure
changes remain relevant; Azure-backed planning from pull-request code was not
adopted.
