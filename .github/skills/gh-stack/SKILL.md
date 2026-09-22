---
name: gh-stack
description: Manage dependent branches and pull requests with the gh-stack extension. Use only for explicit requests to create, inspect, navigate, rebase, sync, or publish a stack.
---

# Stacked Pull Requests

This is the repository's stacked-PR workflow, not the ordinary `ship-it` flow.
Use the installed extension's help and [upstream documentation](https://github.com/github/gh-stack)
for command details rather than maintaining a command manual here.

## Before changing a stack

Inspect the branch, worktree, remotes, and existing stack. Preserve unrelated
changes. Confirm `gh` authentication and extension availability; if the
extension is missing, report the prerequisite rather than silently installing
it or substituting ad-hoc history rewrites.

Agree on the dependency order before creating branches. Each layer should be
independently reviewable, with its code, tests, and directly related docs
together. Use repository branch prefixes and deliberate `git add`/`git commit`,
not shortcuts that stage every change.

## Non-interactive commands

- Supply explicit branch names to `init`, `add`, and `checkout`.
- With a configured prefix, pass only the suffix to `add`.
- Use `view --json` for inspection and `submit --auto` for authorized publishing.
- Select the intended remote explicitly when multiple remotes exist.
- Check the installed command's help if flags or behavior differ. Stop rather
  than entering an interactive prompt or tearing down a conflicting stack.

## Publishing and history changes

Viewing or navigating a stack does not authorize commits, rebases, pushes,
PR changes, or branch deletion. A request to create a stack does not authorize
publishing it.

`push` and `submit` use force-with-lease; `sync` combines rebasing and pushing.
Before these operations, explain which branches will be rewritten or published
and obtain explicit authorization for force-with-lease on those feature
branches. Never force-push `main`, use plain `--force`, or treat an ordinary
"ship it" request as authorization to rewrite history. Stop on divergence or
unexpected remote changes rather than bypassing lease protection.

Before each push, require `uv run poe check` to pass for every changed layer
being published at its final rebased head. Follow
[Quality Gates](../../../docs/contributing.md#quality-gates) for additional
checks. Do not use combined `sync` when it would push rebased heads before these
checks; separate rebase, validation, and publishing.

Review each layer's diff and use the required commit trailers. Ensure each PR
targets its immediate parent branch, with the bottom PR targeting `main`.
Inspect the resulting stack and monitor checks on every published PR.
Merging, pruning branches, and removing local or remote stack metadata require
separate explicit requests.
