---
name: ship-it
description: Validate, commit, push, and open a pull request, then monitor deployment after an explicitly authorized merge. Use for "ship it", "commit and deploy", "push and deploy", or "land this".
---

# Ship It

Deliver the current task without absorbing unrelated worktree changes.

1. Confirm `gh` authentication and inspect the branch and worktree. Never commit
   on `main`; create an appropriately prefixed branch from `main` when needed.
2. Stage only files belonging to the task, then run `uv run poe check`. Run any
   additional CI-equivalent checks required by the changed surfaces (Terraform,
   migrations, curriculum artifacts, or workflow commands).
3. Review the staged diff and commit with a conventional message plus required
   repository trailers.
4. Push without force. If histories diverge, stop rather than rebasing or
   rewriting history automatically.
5. Open a PR to `main` and watch its checks.

Merging is a separate action requiring explicit user intent. If authorized,
prefer squash merge and respect branch protection.

Deployment runs only after deploy-relevant changes merge to `main`. Find the
`deploy.yml` push run by merge SHA, watch it with `gh run watch --exit-status`,
and verify `/health` and `/ready` after success. A skills/docs-only merge may
correctly trigger no deployment.

Use `debug-deploy` for nontrivial failures. Never bypass a failed quality gate,
force-push, or silently include unrelated files.
