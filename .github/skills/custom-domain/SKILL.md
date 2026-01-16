---
name: custom-domain
description: Troubleshoot and fix Azure Container Apps custom domain issues, including SSL certificate binding problems for app.learntocloud.guide. Use when the custom domain is not working after deployment.
---

# Custom Domain Troubleshooting

This skill helps diagnose and fix custom domain issues with Azure Container Apps for `app.learntocloud.guide`.

## How It's Supposed to Work

The custom domain uses **Azure's free managed SSL certificate**, configured in Terraform with the critical `lifecycle.ignore_changes` block:

```hcl
resource "azurerm_container_app_custom_domain" "frontend" {
  name             = var.frontend_custom_domain
  container_app_id = azurerm_container_app.frontend.id

  lifecycle {
    # REQUIRED: Azure modifies these values asynchronously after cert provisioning
    ignore_changes = [certificate_binding_type, container_app_environment_certificate_id]
  }
}
```

**Why `ignore_changes` is required:** Azure provisions the managed certificate asynchronously and updates `certificate_binding_type` and `container_app_environment_certificate_id` outside of Terraform. Without `ignore_changes`, Terraform detects "drift" and tries to recreate the resource, which breaks the binding.

## Diagnostic Commands

### 1. Check Domain Binding Status

```bash
az containerapp hostname list \
  --name ca-ltc-frontend-dev \
  --resource-group rg-ltc-dev \
  --output table
```

**Expected:** `bindingType` should be `SniEnabled`

### 2. Check Certificate Status

```bash
az containerapp env certificate list \
  --name cae-ltc-dev \
  --resource-group rg-ltc-dev \
  --output table
```

**Expected:** `provisioningState` should be `Succeeded`

### 3. Verify DNS Records

```bash
# CNAME should point to frontend FQDN
dig app.learntocloud.guide CNAME +short

# TXT verification record
dig asuid.app.learntocloud.guide TXT +short
```

### 4. Get Expected Values from Terraform

```bash
cd infra
terraform output frontend_fqdn              # CNAME target
terraform output custom_domain_verification_id  # TXT value
```

## Common Issues

### Issue: Domain Works Initially, Breaks After Deployment

**Cause:** Missing `lifecycle.ignore_changes` in Terraform (now fixed).

**Verify the fix is in place:**
```bash
grep -A5 "lifecycle" infra/main.tf | grep -A3 "ignore_changes"
```

### Issue: Certificate Stuck in "Pending"

**Cause:** DNS records incorrect or not propagated.

**Fix:** Verify DNS points to correct values:
```bash
EXPECTED=$(az containerapp show -n ca-ltc-frontend-dev -g rg-ltc-dev --query "properties.configuration.ingress.fqdn" -o tsv)
ACTUAL=$(dig app.learntocloud.guide CNAME +short)
echo "Expected: $EXPECTED"
echo "Actual: $ACTUAL"
```

### Issue: Need to Recreate Domain Binding

If the domain binding is truly broken (rare after the Terraform fix), manually rebind:

```bash
# Remove existing
az containerapp hostname delete \
  -n ca-ltc-frontend-dev -g rg-ltc-dev \
  --hostname app.learntocloud.guide --yes

# Wait for propagation
sleep 10

# Rebind with managed certificate
az containerapp hostname bind \
  -n ca-ltc-frontend-dev -g rg-ltc-dev \
  --hostname app.learntocloud.guide \
  --environment cae-ltc-dev \
  --validation-method CNAME
```

## Terraform State Recovery

If Terraform state is out of sync with Azure:

```bash
cd infra

# Import the existing domain binding
terraform import 'azurerm_container_app_custom_domain.frontend[0]' \
  "/subscriptions/<SUB_ID>/resourceGroups/rg-ltc-dev/providers/Microsoft.App/containerApps/ca-ltc-frontend-dev/customDomainName/app.learntocloud.guide"

# Verify
terraform plan
```

## Environment Variables

| Variable | Dev Value |
|----------|-----------|
| Container App | `ca-ltc-frontend-dev` |
| Resource Group | `rg-ltc-dev` |
| Environment | `cae-ltc-dev` |
| Hostname | `app.learntocloud.guide` |

## Related Files

- [infra/main.tf](../../../infra/main.tf) - Custom domain Terraform config with `lifecycle.ignore_changes`
- [deploy.yml](../../workflows/deploy.yml) - CI/CD workflow
