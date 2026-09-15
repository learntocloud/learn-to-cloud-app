---
description: Triage new issues by suggesting a type and priority.
model: gpt-5-mini
on:
  issues:
    types: [opened, reopened]
permissions:
  contents: read
  issues: read
  copilot-requests: write
tools:
  github:
    toolsets: [issues]
safe-outputs:
  set-issue-type:
    allowed: [Bug, Feature]
    issue-intent: true
    max: 1
  set-issue-field:
    allowed-fields: [Priority]
    issue-intent: true
    max: 1
---

# Triage new issues

Read issue #${{ github.event.issue.number }} and:

1. Classify it as a Bug or Feature.
2. Suggest a Priority based on its user impact and urgency.
3. Include a short rationale and realistic confidence for each change.

Do not post a triage comment. Let the repository's automation level determine
whether each change is applied or held for maintainer review.
