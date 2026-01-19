# Alerting Strategy

This document outlines the monitoring and alerting strategy for the Learn to Cloud application.

## Overview

We use Azure Monitor with Application Insights for observability. Alerts are configured to detect issues early and notify the team via appropriate channels based on severity. The strategy follows industry best practices with **tiered alerting** to reduce alert fatigue.

## Alert Destinations

| Channel | Action Group | Severity | Use Case |
|---------|--------------|----------|----------|
| Email + Page | `ag-ltc-critical-{env}` | Sev1 (Critical) | Immediate response required |
| Email + Slack | `ag-ltc-warning-{env}` | Sev2 (Warning) | Response within hours |

**Tiered Alerting Rationale:**
- Critical alerts (Sev1) require immediate attention and may page on-call
- Warning alerts (Sev2) notify the team but don't interrupt off-hours
- This separation reduces alert fatigue and ensures critical issues get priority

## Severity Levels

| Severity | Meaning | Response Time | Examples |
|----------|---------|---------------|----------|
| **Sev1 (Critical)** | Service degraded or down | Immediate | 5xx errors, container restarts, DB connection failures, circuit breaker extended outage |
| **Sev2 (Warning)** | Resource pressure, may escalate | Within hours | High CPU/memory, storage filling, high latency, circuit breaker open |
| **Sev3 (Info)** | Anomaly detected | Review when convenient | Smart detection anomalies |

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

### Circuit Breaker Alerts

The Clerk authentication circuit breaker protects against extended Clerk outages blocking API worker threads. These alerts monitor circuit breaker state.

| Alert | Severity | Condition | Window | Action Group |
|-------|----------|-----------|--------|--------------|
| **Circuit Open (Warning)** | Sev2 | Circuit opened (JWKS failures) | 5 min | warning |
| **Circuit Open (Critical)** | Sev1 | Circuit open for extended period | 15 min | critical |
| **Circuit Flapping** | Sev1 | >5 state transitions | 10 min | critical |

**Circuit Breaker Behavior:**
- Opens after 5 consecutive JWKS infrastructure failures
- Fails fast for 60 seconds (returns 401 for all auth requests)
- Automatically recovers when Clerk is available again
- Flapping indicates unstable connectivity - may require investigation

## Alert Flow

```
                                    ┌─────────────────┐
                                    │  Sev1 Critical  │
                                    │  (ag-ltc-crit)  │
                                    └────────┬────────┘
                                             │
┌─────────────────┐                          ▼
│  Azure Monitor  │────────────────▶ Email + PagerDuty
│  (metric/query) │                    (immediate)
└────────┬────────┘
         │
         │              ┌─────────────────┐
         │              │  Sev2 Warning   │
         └─────────────▶│  (ag-ltc-warn)  │
                        └────────┬────────┘
                                 │
                                 ▼
                          Email + Slack
                          (within hours)

┌─────────────────┐
│  Azure Portal   │
│  Dashboard      │◀──── All alerts visible
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

### Sev2: Circuit Breaker Open (Warning)

1. Check Clerk status page: https://status.clerk.com
2. Review Application Insights logs for JWKS failure details
3. If Clerk is operational, check network connectivity from Azure
4. Circuit will auto-recover when Clerk is reachable

### Sev1: Circuit Breaker Open (Critical) / Flapping

1. **Immediate:** Clerk authentication is degraded - all auth requests return 401
2. Check Clerk status page: https://status.clerk.com
3. Review circuit breaker metrics in Application Insights
4. If flapping, investigate network instability between Azure and Clerk
5. Consider enabling maintenance mode if extended outage
6. Circuit auto-recovers - no manual intervention needed for recovery

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

# Action Groups (tiered alerting)
resource "azurerm_monitor_action_group" "critical" { ... }  # Sev1 - pages on-call
resource "azurerm_monitor_action_group" "warning" { ... }   # Sev2 - email/Slack

# Metric Alerts
resource "azurerm_monitor_metric_alert" "api_restarts" { ... }    # Sev1 -> critical
resource "azurerm_monitor_metric_alert" "api_high_cpu" { ... }    # Sev2 -> warning
# ... etc

# Query-based Alerts
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "api_5xx_errors" { ... }

# Circuit Breaker Alerts
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "circuit_breaker_open_warning" { ... }
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "circuit_breaker_open_critical" { ... }
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "circuit_breaker_flapping" { ... }

# Smart Detection
resource "azurerm_monitor_smart_detector_alert_rule" "failure_anomalies" { ... }
```

To change alert email:
1. Update `alert_email` in `infra/terraform.tfvars`
2. Run `terraform apply`

To enable Slack notifications for warnings:
1. Create a Slack incoming webhook
2. Set `slack_webhook_url` in `infra/terraform.tfvars`
3. Run `terraform apply`
