# Alert Configuration Guide

This document describes the alert configuration options for the Learn to Cloud application deployment.

## Overview

The application has two levels of alerting:
1. **Azure Infrastructure Alerts** - Monitor Azure resources (Container Apps, PostgreSQL, Application Insights)
2. **GitHub Actions Workflow Alerts** - Get notified about deployment failures

---

## 1. Azure Infrastructure Alerts (RECOMMENDED)

### Current Configuration

Azure Monitor alerts are configured in `infra/resources.bicep` with an Action Group that sends notifications when:
- API Container App error rate exceeds 5%
- Frontend Container App error rate exceeds 5%  
- PostgreSQL CPU usage exceeds 80%
- PostgreSQL storage usage exceeds 80%
- PostgreSQL connection failures occur
- Application Insights detects failed requests (>10 in 15 min)
- Application Insights detects high exception rate (>20 in 15 min)

### Email Configuration

**Method 1: Using Parameter (Recommended)**

1. Update your `infra/main.parameters.json`:
   ```json
   {
     "alertEmailAddress": {
       "value": "your-email@example.com"
     }
   }
   ```

2. The Action Group will automatically send emails to this address when alerts trigger

**Method 2: Using Environment Variable**

Set in GitHub Actions workflow or locally:
```bash
ALERT_EMAIL_ADDRESS=your-email@example.com
```

### Benefits
✅ **Proactive monitoring** - Get alerts before users report issues  
✅ **Infrastructure-specific** - Know exactly which Azure resource has problems  
✅ **Detailed metrics** - CPU, memory, errors, connections, etc.  
✅ **Customizable thresholds** - Adjust alert sensitivity in Bicep files  
✅ **Common Alert Schema** - Structured JSON format for easy parsing  

---

## 2. GitHub Actions Workflow Alerts

### Option A: GitHub Notifications (Default)

GitHub automatically notifies you via:
- **Email** - Sent to your GitHub account email
- **Web notifications** - Bell icon in GitHub UI
- **Mobile app** - GitHub mobile notifications

Configure at: https://github.com/settings/notifications

**Triggers:**
- Workflow failures
- First workflow success after failures
- @mentions in workflow runs

**Pros:** 
- No configuration needed
- Already enabled by default
- Includes workflow logs link

**Cons:**
- Generic notifications
- Not customizable
- May get lost in other GitHub notifications

### Option B: GitHub Actions Notification Action

Add a notification step to your workflow for more control:

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      # ... existing steps ...
      
      - name: Notify on Failure
        if: failure()
        uses: dawidd6/action-send-mail@v3
        with:
          server_address: smtp.gmail.com
          server_port: 465
          username: ${{ secrets.SMTP_USERNAME }}
          password: ${{ secrets.SMTP_PASSWORD }}
          subject: "❌ Deployment Failed: ${{ github.repository }}"
          to: your-email@example.com
          from: GitHub Actions
          body: |
            Deployment to Azure failed!
            
            Repository: ${{ github.repository }}
            Branch: ${{ github.ref_name }}
            Commit: ${{ github.sha }}
            Workflow: ${{ github.workflow }}
            
            View logs: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
```

### Option C: Slack/Discord/Teams Integration

**Slack Example:**
```yaml
- name: Notify Slack
  if: failure()
  uses: slackapi/slack-github-action@v1
  with:
    webhook-url: ${{ secrets.SLACK_WEBHOOK_URL }}
    payload: |
      {
        "text": "❌ Deployment Failed",
        "blocks": [
          {
            "type": "section",
            "text": {
              "type": "mrkdwn",
              "text": "*Deployment Failed*\nRepository: ${{ github.repository }}\nBranch: ${{ github.ref_name }}"
            }
          }
        ]
      }
```

### Option D: Azure Logic Apps / Power Automate

Create a webhook that triggers email/notifications:

```yaml
- name: Notify via Webhook
  if: failure()
  run: |
    curl -X POST "${{ secrets.NOTIFICATION_WEBHOOK_URL }}" \
      -H "Content-Type: application/json" \
      -d '{
        "status": "failed",
        "repository": "${{ github.repository }}",
        "workflow": "${{ github.workflow }}",
        "run_url": "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
      }'
```

---

## 3. Comparison & Recommendations

| Feature | Azure Monitor | GitHub Default | Custom Workflow Action |
|---------|---------------|----------------|------------------------|
| **Setup Effort** | Medium (already configured) | None | Low-Medium |
| **Cost** | Included in Azure | Free | Depends on service |
| **Infrastructure Alerts** | ✅ Yes | ❌ No | ❌ No |
| **Deployment Alerts** | ⚠️ Indirect | ✅ Yes | ✅ Yes |
| **Customization** | High | Low | High |
| **Alert Details** | Very detailed | Basic | Customizable |
| **Email Format** | JSON (Common Alert Schema) | Plain text | Customizable |

### **Recommended Setup:**

**Best Practice: Use Both**

1. **Azure Monitor Alerts** (Already configured) ← Use this for infrastructure health
   - Monitors: CPU, memory, errors, database issues
   - Notifies: When resources are unhealthy
   
2. **GitHub Default Notifications** (Enable in your GitHub settings)
   - Monitors: Workflow success/failure
   - Notifies: When deployments fail
   - Configuration: https://github.com/settings/notifications
     - ✅ Enable "Email" under "Actions"
     - ✅ Enable "Failed workflows only"

This gives you:
- ✅ Deployment failure notifications (GitHub)
- ✅ Runtime/infrastructure issue notifications (Azure)
- ✅ No duplicate notifications
- ✅ Minimal configuration needed

---

## 4. Alert Email Examples

### Azure Monitor Alert Email
```json
{
  "schemaId": "azureMonitorCommonAlertSchema",
  "data": {
    "essentials": {
      "alertRule": "alert-ca-learntocloud-api-dev-error-rate",
      "severity": "Sev2",
      "description": "Alert when API error rate exceeds 5%",
      "monitoringService": "Platform"
    },
    "alertContext": {
      "properties": {},
      "conditionType": "SingleResourceMultipleMetricCriteria"
    }
  }
}
```

### GitHub Actions Notification Email
```
[madebygps/learn-to-cloud-app] Run failed: Deploy to Azure - main

The run failed for the Deploy to Azure workflow in madebygps/learn-to-cloud-app.

View run: https://github.com/madebygps/learn-to-cloud-app/actions/runs/123456
```

---

## 5. Testing Your Alerts

### Test Azure Monitor Alerts
```bash
# Trigger a high CPU alert (requires az cli)
az monitor metrics alert update \
  --name alert-postgres-dev-cpu \
  --resource-group rg-learntocloud-dev \
  --enabled true

# Or manually trigger from Azure Portal:
# Portal → Monitor → Alerts → Alert Rules → [Select Rule] → Test
```

### Test GitHub Actions Alerts
```bash
# Push a change that will fail deployment
git commit --allow-empty -m "test: trigger deployment failure"
git push origin main
```

---

## 6. Troubleshooting

### Not Receiving Azure Alerts?

1. Check Action Group configuration:
   ```bash
   az monitor action-group show \
     --name ag-learntocloud-dev \
     --resource-group rg-learntocloud-dev
   ```

2. Verify email in Action Group:
   - Azure Portal → Monitor → Alerts → Action groups
   - Click your action group
   - Verify email address under "Email/SMS/Push/Voice"

3. Check spam folder and add Azure email to safe senders:
   - `azure-noreply@microsoft.com`

### Not Receiving GitHub Alerts?

1. Check notification settings: https://github.com/settings/notifications
2. Verify email is confirmed in GitHub
3. Check "Actions" section in notification settings
4. Check spam folder and add GitHub to safe senders:
   - `notifications@github.com`

---

## 7. Advanced Configuration

### Alert Severity Levels

Modify in `infra/resources.bicep`:
```bicep
severity: 0  // Critical
severity: 1  // Error
severity: 2  // Warning (current)
severity: 3  // Informational
severity: 4  // Verbose
```

### Custom Alert Thresholds

```bicep
// Adjust error rate threshold
threshold: 5  // 5% error rate (current)
threshold: 10 // 10% error rate (more lenient)
threshold: 1  // 1% error rate (more strict)
```

### Multiple Email Recipients

```bicep
emailReceivers: [
  {
    name: 'PrimaryEmail'
    emailAddress: 'primary@example.com'
    useCommonAlertSchema: true
  }
  {
    name: 'SecondaryEmail'
    emailAddress: 'secondary@example.com'
    useCommonAlertSchema: true
  }
]
```

---

## Summary

**For your use case, the simplest and most effective setup is:**

1. ✅ Keep Azure Monitor alerts configured (already done)
2. ✅ Set `alertEmailAddress` in `main.parameters.json`
3. ✅ Enable GitHub Actions email notifications in your GitHub settings
4. ✅ Done! You'll receive:
   - Azure resource health alerts via email
   - Deployment failure alerts from GitHub
