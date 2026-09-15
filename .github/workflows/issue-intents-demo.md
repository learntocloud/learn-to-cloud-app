---
name: Issue Intents demo
description: Preview type and Priority suggestions for an issue.
on:
  push:
    branches: [madebygps-redesigned-spoon]
    paths:
      - .github/workflows/issue-intents-demo.md
      - .github/workflows/issue-intents-demo.lock.yml
permissions:
  contents: read
  issues: read
  copilot-requests: write
engine:
  id: copilot
  model: copilot/gpt-5-mini
tools:
  bash: true
  cli-proxy: true
  edit: false
  github:
    mode: gh-proxy
    toolsets: [issues]
    read-only: true
    allowed-repos: [learntocloud/learn-to-cloud-app]
    min-integrity: none
safe-outputs:
  staged: true
  activation-comments: false
  report-failure-as-issue: false
  report-failed-jobs: false
  set-issue-type:
    allowed: [Bug, Feature]
    issue-intent: true
    target: "850"
    max: 1
  set-issue-field:
    allowed-fields: [Priority]
    issue-intent: true
    target: "850"
    max: 1
---

# Triage issue #850

Use `gh api repos/${{ github.repository }}/issues/850` to read the issue.

Classify it as a Bug or Feature and choose a Priority of Urgent, High, Medium,
or Low based on user impact and urgency. Include a short evidence-based
rationale and realistic LOW, MEDIUM, or HIGH confidence for each suggestion.

Submit exactly one type and one Priority using the CLI commands below. Replace
the placeholder values with your classifications:

```bash
cat > /tmp/gh-aw/agent/type.json <<'JSON'
{
  "issue_number": 850,
  "issue_type": "Bug",
  "rationale": "Short reason based on the issue.",
  "confidence": "MEDIUM",
  "suggest": true
}
JSON
safeoutputs set_issue_type . < /tmp/gh-aw/agent/type.json

cat > /tmp/gh-aw/agent/priority.json <<'JSON'
{
  "issue_number": 850,
  "field_name": "Priority",
  "value": "Medium",
  "rationale": "Short reason based on impact and urgency.",
  "confidence": "MEDIUM",
  "suggest": true
}
JSON
safeoutputs set_issue_field . < /tmp/gh-aw/agent/priority.json
```

Do not post a comment or modify the issue directly. These outputs are staged
previews and must not change GitHub metadata.
