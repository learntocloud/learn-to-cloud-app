---
name: Agentic workflow smoke test
description: Verify that the Copilot agent runtime can complete a minimal prompt.
on:
  workflow_dispatch:
  push:
    branches: [madebygps-redesigned-spoon]
    paths:
      - .github/workflows/agentic-smoke-test.md
      - .github/workflows/agentic-smoke-test.lock.yml
permissions:
  contents: read
  copilot-requests: write
engine:
  id: copilot
  model: copilot/gpt-5-mini
tools:
  bash: false
  cli-proxy: false
  edit: false
  github: false
safe-outputs:
  activation-comments: false
  report-failure-as-issue: false
  report-failed-jobs: false
  noop:
    report-as-issue: false
---

# Agentic workflow smoke test

Call `safeoutputs.noop` with exactly this message:
`Agentic workflow smoke test passed.`
