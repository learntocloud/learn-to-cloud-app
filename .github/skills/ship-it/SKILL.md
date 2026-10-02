---
name: ship-it
description: Validate, commit, push, and open a pull request, then monitor deployment after an explicitly authorized merge. Use for "ship it", "commit and deploy", "push and deploy", or "land this".
---

# Ship It

Deliver the current task without absorbing unrelated worktree changes.

This workflow is for a single PR to `main`. For explicitly requested stacked
PR delivery, use `gh-stack` instead, including its publishing safeguards.

1. Confirm `gh` authentication and inspect the branch and worktree. Never commit
   on `main`; create an appropriately prefixed branch from `main` when needed.
2. Stage only files belonging to the task. If staged changes touch both
   `infra/**` and application runtime paths (`src/`, `Dockerfile`,
   `pyproject.toml`, `uv.lock`, `package*.json`), stop and split them into two
   PRs: ship the infrastructure PR first, and ship the application PR only after
   its merge and `deploy.yml` run succeed. Then run `uv run poe check`. Follow
   [Quality Gates](../../../docs/contributing.md#quality-gates) for additional
   checks, including API smoke testing after Python application changes.
3. Review the staged diff and commit with a conventional message plus required
   repository trailers.
4. Push without force. If histories diverge, stop rather than rebasing or
   rewriting history automatically.
5. Open a PR to `main` and watch its checks.

Merging is a separate action requiring explicit user intent. If authorized,
prefer squash merge and respect branch protection.

Deployment runs only after deploy-relevant changes merge to `main`. Find the
`deploy.yml` push run for the merge SHA and watch it with
`gh run watch --exit-status`. A run may be replaced while waiting by a newer
one, which releases the newer `main` instead. Verify `/health` and `/ready`
after success. A tests/skills/docs-only merge may correctly trigger no
deployment.

Use `debug-deploy` for nontrivial failures. Never bypass a failed quality gate
or silently include unrelated files.
