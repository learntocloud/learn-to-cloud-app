---
on:
  schedule: weekly on monday
  workflow_dispatch:

description: >
  Weekly audit of all external URLs in Learn to Cloud content YAML files.
  Checks for broken links and redirects.

engine: copilot

steps:
  - name: Checkout content files
    uses: actions/checkout@v4
    with:
      sparse-checkout: |
        content/phases
        .github/workflows
      sparse-checkout-cone-mode: true

permissions:
  contents: read

tools:
  github:
    toolsets: [repos]
    read-only: true
  bash: ["cat", "find", "grep", "head", "tail", "wc", "echo", "sort", "uniq", "ls", "sed", "awk", "yq", "which", "python3", "curl"]
  web-fetch:

network:
  allowed:
    - defaults
    - github
    # Video
    - "*.youtube.com"
    - "*.youtu.be"
    # Cloud providers
    - "*.microsoft.com"
    - "*.amazon.com"
    - "*.aws"
    - "*.google.com"
    # Learning platforms
    - "*.freecodecamp.org"
    - "*.khanacademy.org"
    - "*.kodekloud.com"
    - "*.geeksforgeeks.org"
    - "*.dev.to"
    # Docs & tools
    - "*.linux.com"
    - "*.opensource.com"
    - "*.hashicorp.com"
    - "*.docker.com"
    - "*.kubernetes.io"
    - "*.k8s.io"
    - "*.terraform.io"
    - "*.terraform-best-practices.com"
    - "*.tiangolo.com"
    - "*.sqlalchemy.org"
    - "*.postgresql.org"
    - "*.cloudflare.com"
    - "*.prometheus.io"
    - "*.grafana.com"
    - "*.uvicorn.org"
    - "*.caddyserver.com"
    - "*.modelcontextprotocol.io"
    - "*.n8n.io"
    # Developer tools
    - "*.visualstudio.com"
    - "*.github.io"
    - "*.atlassian.com"
    - "*.jetbrains.com"
    - "*.ibm.com"
    # Other
    - "*.aka.ms"
    - "*.httpbin.org"
    - "*.overthewire.org"
    - "*.subnetipv4.com"
    - "*.nostarch.com"
    - "*.certbot.eff.org"

safe-outputs:
  create-issue:
    title-prefix: "[content-audit] "
    labels: [content, automation]
    close-older-issues: true
---

# Content Link Auditor

You are a content quality auditor for the Learn to Cloud curriculum.

## Goal

Audit every external URL found in the content YAML files under `content/phases/` and produce a report identifying broken links, permanent redirects, and potentially retired resources.

## Process

### Step 1: Extract all URLs

Only verify **resource links** (the URLs learners click), which are represented as YAML `url:` fields in the content.

Important: do **not** rely on `**` globbing (globstar is often disabled in non-interactive shells). Use `find` to enumerate files.

Preferred extraction (robust; preserves file + line number context):

```bash
find content/phases -type f \( -name "*.yaml" -o -name "*.yml" \) -print0 | \
  xargs -0 -n 50 grep -RInE '^[[:space:]]*url:[[:space:]]*https?://' | \
  sort -u
```

To build a deduplicated list of URLs only:

```bash
find content/phases -type f \( -name "*.yaml" -o -name "*.yml" \) -print0 | \
  xargs -0 -n 50 grep -RInE '^[[:space:]]*url:[[:space:]]*https?://' | \
  sed -E 's/^[^:]+:[0-9]+:[[:space:]]*url:[[:space:]]*//' | \
  sort -u
```

URLs can appear in many YAML fields (the schema evolves). Historically common locations include:
- `learning_steps[].url`
- `learning_steps[].options[].url`
- `security_overviews[].url` (often in `_phase.yaml`)

Ignore template/placeholder URLs and non-external/local URLs, including (but not limited to):
- `https://github.com/your-username`, `https://github.com/username`, `https://github.com/yourname`, etc.
- `http://localhost`, `http://127.0.0.1`, `http://host.docker.internal`, `http://0.0.0.0`
- Any URL under an explicit `placeholder:` key (these are user prompts, not curriculum resources)

### Step 2: Check each URL

For each unique URL, use the `web-fetch` tool to check if the page loads successfully.

**Important:** Do NOT try to install Python packages or use `pip` or `wget`. Prefer the `web-fetch` tool for URL checks. If `web-fetch` is denied in non-interactive mode, use `curl` as the fallback (HEAD first, then GET with redirect-follow if needed). Use `yq` for YAML parsing and `sed`/`awk` for text processing.

Classify results as:

- **Working** (200): Record as healthy.
- **Redirect** (301/302): If `web-fetch` returns content from a different URL than requested, record it as a redirect. Flag permanent redirects — the YAML should be updated to the new URL.
- **Broken** (404, 410, connection error, timeout): If `web-fetch` fails or returns an error, record as broken with the error.
- **Soft 404**: If the page loads but the content is clearly a "page not found" or "content removed" message, flag it.

For YouTube URLs (`youtu.be`, `youtube.com`), a 200 response is sufficient — don't try to parse the page content.

### Step 3: Generate the report

Create a GitHub issue with the findings. Structure the issue body as:

```markdown
## Content Link Audit — {date}

**Scanned:** {N} unique URLs across {M} YAML files
**Healthy:** {count} | **Broken:** {count} | **Redirects:** {count}

### 🔴 Broken Links

| File | Field | URL | Error |
|------|-------|-----|-------|
| phase0/linux.yaml | learning_steps[1].url | https://... | 404 Not Found |

### 🟡 Permanent Redirects

| File | Field | Current URL | Redirects To |
|------|-------|-------------|--------------|
| ... | ... | ... | ... |

### ✅ Summary

All {N} other links are healthy.

### Recommended Actions
- [ ] Update redirected URLs to their final destinations
- [ ] Remove or replace broken links
```

## Important Guidelines

- This workflow must ONLY verify resource link health (working/broken/redirect). Do not audit certifications, difficulty, correctness, or any other content quality dimensions.
- Do NOT create an issue if everything is healthy — use the noop output instead with a message like "All {N} links healthy, no issues found."
- Group related broken links by phase for easier fixing.
- Be conservative: only flag a link as broken if you're confident it's not a transient error. If a URL times out once, note it as "possibly broken" rather than definitely broken.
- For YouTube videos, only flag if the response is clearly a 404 or removed video — don't flag age-restricted or region-locked content.
