## Plan: Auto-Populate Verification URLs

Use the authenticated user's stored `github_username` to prefill GitHub-based verification inputs, while preserving editable inputs and existing server-side validation. The key finding is that fork source repos are already encoded via `required_repo`, so most of this can be implemented without new content metadata.

**Steps**

1. Confirm the requirement-card render context has access to the authenticated user or GitHub username; if not, pass the smallest necessary `github_username` value into the card context.
2. Add a pure helper to derive default submission URLs from `HandsOnRequirement` + `github_username`.
3. Implement derivation rules:
   - `GITHUB_PROFILE` → `https://github.com/{username}`
   - `PROFILE_README` → match current validator/placeholder expectation, either repo URL or README blob URL
   - `REPO_FORK` → derive repo name from `required_repo`, e.g. `learntocloud/linux-ctfs` → `https://github.com/{username}/linux-ctfs`
   - Token/deployed API submissions → no default
   - PR/LLM repo submissions → only default if the target repo is safely derivable
4. If phases 3/5/6 need `journal-starter` and it is not safely derivable, add an optional `default_repo` field to `HandsOnRequirement` and populate only those YAML requirements.
5. Update the requirement card input to render the computed default as `value` only when no previous submission value exists.
6. Add tests for helper behavior, missing username, malformed/missing repo metadata, and template rendering if a suitable pattern exists.
7. Validate with targeted `uv run pytest`, then `uv run ruff check` / `uv run ruff format --check` for changed Python files.

**Relevant Files**

- `api/templates/partials/requirement_card.html` — verification input rendering.
- `api/routes/htmx_routes.py` — authenticated user/GitHub username flow and card rendering.
- `api/schemas.py` — `HandsOnRequirement`, including existing `required_repo`.
- `api/services/verification/requirements.py` — likely helper placement if defaults belong near requirement logic.
- `api/services/verification/github_profile.py` — existing GitHub URL parsing and validators.
- `content/phases/phase1/_phase.yaml`, `content/phases/phase2/_phase.yaml`, `content/phases/phase3/_phase.yaml`, `content/phases/phase5/_phase.yaml`, `content/phases/phase6/_phase.yaml` — repo metadata/default candidates.

**Decisions**

- Reuse OAuth-backed `User.github_username`; do not infer usernames client-side.
- Keep validation authoritative on the server; autopopulation is UX/security hardening only.
- Prefer deriving from existing `required_repo`; add new YAML metadata only where unavoidable.
- Exclude new pages, modals, API discovery calls, or non-requested UI features.
