# Azure Deployment Plan

> **Status:** Ready for Validation

Generated: 2026-05-07

---

## 1. Project Overview

**Goal:** Add frontend/browser Application Insights Real User Monitoring (RUM) to the existing FastAPI-served Jinja/HTMX UI without mixing it with backend API telemetry.

**Path:** Add Components

---

## 2. Requirements

| Attribute | Value |
|-----------|-------|
| Classification | Production |
| Scale | Small |
| Budget | Cost-Optimized |
| **Subscription** | Visual Studio Enterprise Subscription / `96e40cb1-d5eb-46c6-b0fd-8e64eb9c119d` |
| **Location** | `centralus` |

User-confirmed frontend telemetry decisions:

| Decision | Value |
|----------|-------|
| Hosting | Existing FastAPI/Jinja/HTMX UI deployed with the API on Azure Container Apps |
| App Insights resource | Separate frontend Application Insights resource |
| Browser SDK cookies/storage | Disabled |
| SDK loading | Microsoft-hosted loader CDN |
| Browser user identifier | Do not send an authenticated user identifier |

---

## 3. Components Detected

| Component | Type | Technology | Path |
|-----------|------|------------|------|
| API-hosted UI | Frontend | Jinja2 templates, HTMX, Alpine.js, static JavaScript | `api/src/learn_to_cloud/templates`, `api/src/learn_to_cloud/static` |
| FastAPI API | API | Python 3.13, FastAPI, Azure Monitor OpenTelemetry | `api/src/learn_to_cloud` |
| Infrastructure | IaC | Terraform, Azure Container Apps, Azure Monitor | `infra` |

---

## 4. Recipe Selection

**Selected:** Terraform

**Rationale:** The existing production infrastructure is already managed in `infra/` with Terraform. The frontend telemetry resource should be added to the existing resource group, share the existing Log Analytics workspace, and be passed to the existing API Container App as configuration.

---

## 5. Architecture

**Stack:** Azure Container Apps with server-rendered frontend

### Service Mapping

| Component | Azure Service | SKU |
|-----------|---------------|-----|
| Frontend browser telemetry | Azure Application Insights `azurerm_application_insights.frontend` | Consumption / workspace-based |
| Existing API-hosted UI | Azure Container Apps `azurerm_container_app.api` | Existing app |
| Central telemetry storage | Existing Log Analytics workspace | `PerGB2018` |

### Supporting Services

| Service | Purpose |
|---------|---------|
| Log Analytics | Centralized telemetry workspace shared by backend and frontend App Insights resources |
| Application Insights (frontend) | Browser RUM telemetry: page views, JS exceptions, HTMX client errors, AJAX dependencies |
| Application Insights (backend) | Existing API/server telemetry, unchanged |
| Container Apps | Hosts the FastAPI app and serves the Jinja/HTMX frontend |

### Frontend Telemetry Design

- Add a separate workspace-based Application Insights resource for browser telemetry.
- Pass its connection string to the API container using a non-secret environment variable such as `FRONTEND_APPLICATIONINSIGHTS_CONNECTION_STRING`.
- Add a shared settings field and Jinja context so `base.html` can emit telemetry config only when the frontend connection string is configured.
- Use the Microsoft Application Insights JavaScript loader from `https://js.monitor.azure.com/scripts/b/ai.3.gbl.min.js`.
- Disable SDK cookies and browser storage with SDK config.
- Do not call `setAuthenticatedUserContext` and do not emit GitHub usernames or internal user IDs from browser telemetry.
- Track initial page view and HTMX boosted navigation/page swaps explicitly, while avoiding duplicate automatic route tracking.
- Track HTMX client-side response errors as browser events/exceptions.
- Update CSP narrowly for the Microsoft loader and the frontend ingestion endpoint required by the generated connection string.

---

## 6. Provisioning Limit Checklist

**Purpose:** Validate that the selected subscription and region have sufficient quota/capacity for all resources to be deployed.

### Phase 1: Resource Inventory

| Resource Type | Number to Deploy | Total After Deployment | Limit/Quota | Notes |
|---------------|------------------|------------------------|-------------|-------|
| `Microsoft.Insights/components` | 1 | 2 in `rg-ltc-dev` | 800 resources per resource group per resource type | Azure quota CLI extension failed to install in this environment, so capacity validation used Azure resource listing plus the Azure Resource Manager documented per-resource-type resource group limit. Existing resource group currently has 1 Application Insights component. |

### Phase 2: Quotas and Capacity

| Check | Result |
|-------|--------|
| Azure quota CLI attempted first | Failed because the `quota` extension failed to install via Azure CLI/Pip in this environment |
| Current usage source | `azure-group_resource_list` for `rg-ltc-dev` showed 1 existing `Microsoft.Insights/components` resource |
| Fallback limit source | Azure Resource Manager limits documentation: resources per resource group, per resource type = 800 |
| Capacity calculation | 1 existing + 1 new = 2, below 800 |
| Status | ✅ All planned resources within documented limits |

---

## 7. Execution Checklist

### Phase 1: Planning

- [x] Analyze workspace
- [x] Gather requirements
- [x] Confirm subscription and location with user
- [x] Prepare resource inventory
- [x] Fetch quotas and validate capacity using quota CLI first, then documented fallback
- [x] Scan codebase
- [x] Select recipe
- [x] Plan architecture
- [x] User approved this plan

### Phase 2: Execution

- [x] Research components
- [x] Add Terraform frontend Application Insights resource and outputs
- [x] Add frontend telemetry settings/context
- [x] Add browser telemetry loader/config in `base.html`
- [x] Add HTMX/client-side telemetry hooks
- [x] Update CSP for Microsoft loader and ingestion endpoint
- [x] Validate local rendering and quality gates
- [x] Update plan status to `Ready for Validation`

### Phase 3: Validation

- [ ] Invoke azure-validate skill
- [ ] All validation checks pass
- [ ] Update plan status to `Validated`
- [ ] Record validation proof below

### Phase 4: Deployment

- [ ] Invoke azure-deploy skill after validation when ready to deploy
- [ ] Deployment successful
- [ ] Report deployed endpoint URLs
- [ ] Update plan status to `Deployed`

---

## 8. Validation Proof

| Check | Command Run | Result |
|-------|-------------|--------|
| Terraform formatting | `terraform -chdir=infra fmt -check` | Passed |
| API/shared ruff lint | `cd api && uv run ruff check . ../packages/learn-to-cloud-shared` | Passed |
| Verification Functions ruff lint | `cd apps/verification-functions && uv run ruff check .` | Passed |
| API/shared ruff format | `cd api && uv run ruff format --check . ../packages/learn-to-cloud-shared` | Passed |
| Verification Functions ruff format | `cd apps/verification-functions && uv run ruff format --check .` | Passed |
| API type check | `cd api && uv run ty check --exclude scripts --exclude tests .` | Passed |
| Shared type check | `cd packages/learn-to-cloud-shared && uv run ty check --exclude tests .` | Passed |
| Verification Functions type check | `cd apps/verification-functions && uv run ty check .` | Passed |
| API startup and smoke tests | `/health`, `/ready`, `/openapi.json` against local uvicorn | Passed |
| API/shared tests | `cd api && uv run pytest tests/ ../packages/learn-to-cloud-shared/tests -x --tb=short` | Passed, 642 tests |
| Verification Functions import | `cd apps/verification-functions && uv run python -c "import function_app"` | Passed |

**Validated by:** Local repository validation. Pending azure-validate skill before deployment.

---

## 9. Files to Generate or Modify

| File | Purpose | Status |
|------|---------|--------|
| `.azure/deployment-plan.md` | This plan | ✅ |
| `infra/monitoring.tf` | Add separate frontend Application Insights resource | ✅ |
| `infra/container-apps.tf` | Pass frontend telemetry connection string to API container | ✅ |
| `infra/outputs.tf` | Expose frontend App Insights details | ✅ |
| `packages/learn-to-cloud-shared/src/learn_to_cloud_shared/core/config.py` | Add frontend telemetry setting | ✅ |
| `api/src/learn_to_cloud/core/templates.py` | Inject frontend telemetry config into templates | ✅ |
| `api/src/learn_to_cloud/core/middleware.py` | Update CSP for frontend telemetry | ✅ |
| `api/src/learn_to_cloud/templates/base.html` | Load and configure browser SDK | ✅ |
| `api/src/learn_to_cloud/static/js/frontend-telemetry.js` | HTMX/client telemetry hooks | ✅ |
| Relevant tests | Cover config/context/CSP where practical | ✅ |

---

## 10. Next Steps

> Current: Ready for azure-validate before deployment

1. Invoke azure-validate before deployment.
2. Invoke azure-deploy only after validation when ready to deploy.
