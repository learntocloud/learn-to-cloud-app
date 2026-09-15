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
safe-outputs: {}
---

# Agentic workflow smoke test

Reply with exactly: Agentic workflow smoke test passed.
