# Maintainer Guide

For everyday development, start with [Contributing](contributing.html).

## Azure and Terraform

Infrastructure work needs Azure CLI, GitHub CLI, and the Terraform version
selected in the
[`CI workflow`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/.github/workflows/ci.yml).
Database investigations also need `jq` and `psql`. These are not required for
ordinary application development.

Check the signed-in account and subscription before operational work:

```bash
az account show --output table
terraform version
gh auth status
```

Use the repository's
[`review-terraform` procedure](https://github.com/learntocloud/learn-to-cloud-app/blob/main/.github/skills/review-terraform/SKILL.md)
for plans and permission review. Planning does not authorize applying or changing
state. Production deployment runs through
[`app-deploy.yml`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/.github/workflows/app-deploy.yml).

## Optional Copilot tooling

The
[`skill directory`](https://github.com/learntocloud/learn-to-cloud-app/tree/main/.github/skills)
owns workflow instructions and authorization boundaries. Consult the relevant
skill rather than maintaining a second command reference here.

Install only the integrations you use, as configured in
[`.mcp.json`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/.mcp.json).
Browser QA uses a separate Playwright Python installation; follow
[Testing](testing.html#dog-food-agent-ai-powered-qa), not MCP browser setup.

## Issue triage

Edit
[`issue-triage.md`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/.github/workflows/issue-triage.md),
then compile and commit its generated `.lock.yml` alongside it. Never edit the
generated workflow by hand.

```bash
gh aw --version
gh aw compile
```

Review the generated diff, especially permissions, credential requirements,
allowed outputs, and pinned actions. Upgrade the compiler intentionally rather
than treating regenerated output as harmless formatting.
The current compiled workflow requires `COPILOT_GITHUB_TOKEN`; keep setup aligned
with the generated workflow rather than assuming a different inference mode.

Organization owners manage issue types and the Priority field under
**Organization Settings > Planning**. **Agent suggestions for issues** controls
whether suggestions apply automatically or await review. After an authorized
workflow change, use a clearly marked test issue to confirm the expected type and
Priority suggestions without comments or assignments.

## GitHub Pages

The
[`Pages workflow`](https://github.com/learntocloud/learn-to-cloud-app/blob/main/.github/workflows/pages.yml)
builds `docs/` on pull requests and publishes relevant `main` changes to
[the documentation site](https://learntocloud.github.io/learn-to-cloud-app/).
It also supports manual publishing.

Keep **Pages > Build and deployment > Source** set to **GitHub Actions**.
Use `.html` links between published guides, and repository links for source
files. Keep the [index](index.html) current and preserve section anchors used by
alert descriptions, workflows, and agent instructions.
