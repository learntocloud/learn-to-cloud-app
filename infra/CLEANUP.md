# Terraform cleanup backlog

Tracked findings from a full review of `infra/`. Ordered by priority. Check items
off as they land; each tier is intended to ship as its own pull request.

`terraform fmt` is clean and the module layout is sensible — everything below is
about credentials in state, exposure defaults, and structure.

## Tier 1 — Security

- [x] **Function storage uses an access key.** `functions.tf` sets
      `storage_authentication_type = "StorageAccountConnectionString"` and
      `storage_access_key = azurerm_storage_account.verification_functions.primary_access_key`,
      which writes a reusable storage key into Terraform state and forces the
      planning identity to hold `listKeys`.

      **Blocked on a provider limitation.** Switching to
      `storage_authentication_type = "UserAssignedIdentity"` fixes the
      *deployment* container only. AzureRM always writes the host storage
      setting from a key-based connection string, in both 4.81 and 5.0.1:
      `function_app_flex_consumption_resource.go:450` builds
      `StorageStringFmt` (`...;AccountKey=%s;...`) from `storage_access_key`
      regardless of the authentication type, and
      `helpers/function_app_schema.go:2114` writes that value to
      `AzureWebJobsStorage` unconditionally. With the key removed the app would
      receive `AccountKey=` and the Functions host would fail to resolve the
      connection. The provider's own acceptance tests
      (`storageUserAssignedIdentity1`) only assert the resource exists, not that
      the host starts. Fully key-free therefore requires moving the Function App
      to `azapi_resource`, which the repository already uses for Foundry and the
      Durable Task Scheduler.

      **Resolved** by modelling the app with azapi and migrating state with
      `removed` + `import`. One caveat to confirm at apply time: azapi PUTs only
      the configured body, so compare the site's ARM properties before and after
      the first apply to be sure the Web RP did not reset an omitted property.
- [x] **`smoke_test_token` is an inline Container App secret.** `container-apps.tf`
      passes the raw value through `var.smoke_test_token` (supplied by CI as
      `TF_VAR_smoke_test_token`), so it lands in state in plaintext. Note that an
      `azurerm_key_vault_secret` resource would not help — that also stores the
      value in state. The fix is to stop routing the token through Terraform:
      create the Key Vault secret out of band, exactly like the other four
      secrets, reference it with `key_vault_secret_id`, and delete the variable.
      This also removes the two `dynamic` blocks and the `!= ""` special-casing.
- [ ] **PostgreSQL is reachable from all of Azure.** `database.tf` combines
      `public_network_access_enabled = true` with an `AllowAzureServices`
      (`0.0.0.0`) firewall rule, so any Azure tenant can reach the server and
      Entra-only authentication is the sole control. **Depends on a networking
      decision:** the Container Apps environment and the Flex Consumption app
      both egress from dynamic public IPs today, so there is no address range to
      allow-list. Closing this requires VNet integration, or a NAT gateway for a
      stable egress address, or private networking.
- [ ] **Durable Task Scheduler allowlist defaults to `0.0.0.0/0`.** The
      `variables.tf` precondition only rejects it in `prod`, and CI never sets
      `TF_VAR_durable_task_scheduler_ip_allowlist`, so the open default is what
      dev actually runs. Same networking dependency as the item above.
- [x] **Key Vault reference identity is implicit.** `key-vault.tf` grants
      `Key Vault Secrets User` to the Functions app's *system-assigned* identity
      while the app otherwise runs as its user-assigned identity. Key Vault
      references only resolve because the reference identity is unset and
      defaults to system-assigned. `azurerm_function_app_flex_consumption` has no
      `key_vault_reference_identity_id` argument in either 4.81 or 5.0.1, so
      making this explicit needs `azapi` — the same conclusion as the storage
      item above. Resolved by the same azapi migration: the app now runs with
      the user-assigned identity only, and keyVaultReferenceIdentity points at
      it explicitly.

- [x] **Disable Shared Key on the Functions storage account.** Set
      `shared_access_key_enabled = false` after the dev apply confirmed the host
      indexes all 12 functions with identity-based storage and no `AccountKey=`
      remains in app settings. `azurerm_storage_container` uses
      `storage_account_id`, so it goes through the management plane and keeps
      working without the key.

      `azurerm_storage_account` itself still reads queue properties over the
      data plane, which 403s once the key is gone, so the provider needs
      `storage_use_azuread = true`. That makes the read use Entra ID, which
      requires a data-plane role: the CI identities are granted
      `Storage Queue Data Contributor` (apply) and `Storage Queue Data Reader`
      (plan) on the account. These are granted out of band, alongside the OIDC
      federation and the subscription Contributor/Reader assignments, because
      Terraform cannot refresh this resource without them.
- [x] **Diagnostic settings.** Added for Key Vault, the container registry,
      PostgreSQL, and the Functions storage blob service. None of these resource
      types expose Azure Monitor category groups, so categories are named
      explicitly.
- [ ] **No network restrictions.** Key Vault and the Functions storage account
      both allow public network access with no `network_acls`. Blocked on the
      same networking decision as the PostgreSQL item.

## Tier 2 — Structure

- [ ] **`provider.tf` holds four unrelated concerns:** the `terraform` block, the
      provider configurations, a real resource (`random_string.suffix`), and a
      30-line `locals`. Split into `versions.tf`, `providers.tf`, and `locals.tf`.
- [ ] **`monitoring.tf` is 479 lines** with eight near-identical
      `azurerm_monitor_scheduled_query_rules_alert_v2` blocks. Collapse them into
      a `for_each` over a locals map of alert definitions.
- [ ] **`default = null` + `coalesce()` indirection.** Roughly ten variables
      declare a null default and resolve the real default in `locals`. Put the
      default on the variable and drop the local, keeping the pattern only where
      the value genuinely varies per environment.
- [x] **`required_version = ">= 1.5.0"`** was unbounded while local and CI runs used
      1.14. Pinned to `~> 1.14`, and the CI/apply jobs to `~1.14`. The old `~1.5`
      workflow pin resolved to 1.5.x, which predates expression support in
      `import` block ids (added in 1.12).
- [x] **Container Apps Job refresh reads secrets.** Replaced
      `azurerm_container_app_job.migrations` with `azapi_resource` so refresh
      uses the normal ARM resource read instead of
      `Microsoft.App/jobs/listSecrets/action`. The state migration uses
      `removed` + `import` and preserves the live job, managed identity,
      registry identity, image rollout boundary, and runtime configuration.
- [x] **API Container App refresh reads secrets.** AzureRM also calls
      `Microsoft.App/containerApps/listSecrets/action` during every refresh.
      Replaced `azurerm_container_app.api_v5` with `azapi_resource.api`, while
      preserving the user-assigned identity, Key Vault references, registry,
      ingress, custom-domain bindings, scaling, probes, and deployment-managed
      image. The migration uses `removed` + `import` and must land before the
      read-only PR plan workflow is enabled.

## Tier 3 — Consistency

- [ ] **`local.suffix` is applied inconsistently.** Key Vault, PostgreSQL, ACR,
      Log Analytics, App Insights, storage, and Foundry include it; the Container
      App, migration job, Function App, service plan, Container App environment,
      and action group do not. Pick one rule and document it.
- [ ] **`outputs.tf` mixes conventions.** `AZURE_RESOURCE_GROUP` and
      `AZURE_CONTAINER_REGISTRY_*` are SCREAMING_CASE among otherwise snake_case
      outputs, and `database_host` overlaps `postgres_server_name`. Normalize to
      snake_case and map names in the workflow instead.
- [ ] **`schema_validation_enabled = false` is copy-pasted** onto five
      `azapi_resource` blocks, including stable API versions that do not need it.
      The Container Apps Job migration uses the stable schema with validation
      enabled; clean up the older resources separately.
- [x] **`provider "azapi" {}` is empty.** Set `subscription_id` so it cannot drift
      from the AzureRM provider.
- [ ] **Duplicated and hardcoded values.** `https://learntocloud.guide` appears in
      both `container-apps.tf` (CORS) and `monitoring.tf` (web test); the
      verification Entra client ID and the dashboard reader group object ID are
      hardcoded in `provider.tf` locals and `variables.tf` defaults.
- [ ] **`ignore_changes = all` on `random_string.suffix`** is broader than needed
      for an already-stable value.
- [ ] **Redundant `depends_on`.** `container-apps.tf` and `migrations.tf` both
      declare an explicit dependency on
      `azurerm_postgresql_flexible_server_database.main`, which is already
      implicit through env var references. Keep only the role-assignment entries.
- [ ] **No Terraform checks in the quality gate.** Add `terraform validate` and a
      linter (`tflint`, optionally `checkov`) to the `poe` tasks and CI.

## Related work

- Issue #741 owns the final read-only plan proof. Remove
  `migrate-container-app-job.tf` and `migrate-container-app-azapi.tf` only after
  the state migrations have been applied to every environment and a
  refresh-enabled plan succeeds without `listKeys` or `listSecrets`.
- PR #714 bumps AzureRM 4.81 to 5.0.1. Land the cleanup on 4.x first, then
  upgrade, so a provider major and a state migration never mix in one change.
