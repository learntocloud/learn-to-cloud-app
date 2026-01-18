# Alerting Strategy

This document outlines the monitoring and alerting strategy for the Learn to Cloud application.

## Overview

We use Azure Monitor with Application Insights for observability. Alerts are configured to detect issues early and notify the team via email. The strategy prioritizes **availability over noise** — we alert on first failure for critical issues.

## Alert Destinations

| Channel | Recipient | Use Case |
|---------|-----------|----------|
| Email | `learntocloudguide@gmail.com` | All alerts (Sev1 and Sev2) |

**Action Group:** `ag-ltc-critical-{env}`

## Severity Levels

| Severity | Meaning | Response Time | Examples |
|----------|---------|---------------|----------|
| **Sev1 (Critical)** | Service degraded or down | Immediate | 5xx errors, container restarts, DB connection failures |
| **Sev2 (Warning)** | Resource pressure, may escalate | Within hours | High CPU/memory, storage filling, high latency |

## Alert Categories

### API Alerts (Container App)

| Alert | Severity | Condition | Window | Frequency |
|-------|----------|-----------|--------|-----------|
| **5xx Errors** | Sev1 | Any 5xx response code | 5 min | 5 min |
| **Container Restarts** | Sev1 | RestartCount > 0 | 5 min | 1 min |
| **High CPU** | Sev2 | CPU > 80% | 15 min | 5 min |
| **High Memory** | Sev2 | Memory > 80% | 15 min | 5 min |
| **High Latency** | Sev2 | Avg response > 2s | 5 min | 5 min |

**Thresholds explained:**
- CPU threshold: 400M nanocores (80% of 0.5 CPU allocated)
- Memory threshold: 858MB (80% of 1Gi allocated)
- Latency threshold: 2000ms average

### Database Alerts (PostgreSQL)

| Alert | Severity | Condition | Window | Frequency |
|-------|----------|-----------|--------|-----------|
| **Connection Failures** | Sev1 | connections_failed > 0 | 5 min | 1 min |
| **High Storage** | Sev2 | storage_percent > 80% | 1 hour | 15 min |
| **High CPU** | Sev2 | cpu_percent > 80% | 15 min | 5 min |

### Smart Detection (AI-Powered)

| Alert | Severity | Description |
|-------|----------|-------------|
| **Failure Anomalies** | Sev3 | AI detects unusual spike in failures |

Azure's Smart Detection uses machine learning to identify anomalies without manual threshold configuration. It automatically adapts to traffic patterns. The detector is auto-created by Azure when Application Insights is provisioned — we import and manage it via Terraform to link our action group.

## Alert Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Azure Monitor  │────▶│  Action Group   │────▶│  Email          │
│  (metric/query) │     │  (ag-ltc-crit)  │     │  Notification   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │
        │ Sev1: Immediate
        │ Sev2: Batched (up to 5 min)
        ▼
┌─────────────────┐
│  Azure Portal   │
│  Dashboard      │
│  (dash-ltc-dev) │
└─────────────────┘
```

## Dashboard

The monitoring dashboard (`dash-ltc-{env}`) provides at-a-glance visibility:

| Panel | Metrics | Purpose |
|-------|---------|---------|
| **API Request Rate** | requests/count | Traffic volume |
| **API Failed Requests** | requests/failed | Error rate |
| **API Response Time** | requests/duration (avg) | Performance |
| **Database CPU %** | cpu_percent | DB health |
| **Database Connections** | active_connections | Connection pool usage |
| **Database Storage %** | storage_percent | Capacity planning |

**Access:** Azure Portal → Dashboards → `dash-ltc-{env}`

Or use the Terraform output: `terraform output dashboard_url`

## Response Procedures

### Sev1: 5xx Errors

1. Check Application Insights → Failures for stack traces
2. Review recent deployments in GitHub Actions
3. Check Container App logs: `az containerapp logs show -n ca-ltc-api-dev -g rg-ltc-dev`
4. If migration-related, check `/ready` endpoint and `init_error` in logs

### Sev1: Container Restarts

1. Check Container App events for OOM or crash reasons
2. Review memory/CPU metrics before restart
3. Check for startup probe failures (migration timeout?)
4. Review recent code changes

### Sev1: Database Connection Failures

1. Check PostgreSQL metrics for connection count vs. limit
2. Verify Entra ID token acquisition in API logs
3. Check for network issues (firewall rules, VNet)
4. Review connection pool settings in API config

### Sev2: High CPU/Memory

1. Check if traffic spike is causing the load
2. Review slow queries in Application Insights → Dependencies
3. Consider scaling: increase `max_replicas` in Terraform
4. Identify memory leaks via heap profiling

### Sev2: High Latency

1. Check Application Insights → Performance for slow operations
2. Review database query times
3. Check external dependency latency (Clerk, Google API)
4. Consider caching or query optimization

### Sev2: Database Storage

1. Review table sizes: `SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) FROM pg_catalog.pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC;`
2. Clean up old data if applicable
3. Increase storage in Terraform (`storage_mb` variable)

## Not Alerting On

These are intentionally not configured as alerts:

| Metric | Reason |
|--------|--------|
| 4xx errors | Expected for auth failures, not-found, etc. |
| Replica scaling | Normal auto-scale behavior |
| Low traffic | Not necessarily a problem |
| Business metrics | May add later (user registration drops, etc.) |

## Future Improvements

- [ ] Add Discord webhook integration
- [ ] Add business metric alerts (zero registrations in 24h)
- [ ] Add synthetic monitoring (availability tests)
- [ ] Add cost alerts (budget thresholds)
- [ ] Add auto-remediation runbooks (restart container on OOM)

## Configuration

All alerting is defined in Terraform:

```hcl
# infra/main.tf

# Action Group
resource "azurerm_monitor_action_group" "critical" { ... }

# Metric Alerts
resource "azurerm_monitor_metric_alert" "api_restarts" { ... }
resource "azurerm_monitor_metric_alert" "api_high_cpu" { ... }
# ... etc

# Query-based Alerts
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "api_5xx_errors" { ... }

# Smart Detection
resource "azurerm_monitor_smart_detector_alert_rule" "failure_anomalies" { ... }
```

To change alert email:
1. Update `alert_email` in `infra/terraform.tfvars`
2. Run `terraform apply`
