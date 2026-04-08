# Plan: Auto-Populate Verification URLs from GitHub Username

## TL;DR
Pre-fill the GitHub repo URL input field on verification forms using the authenticated user's `github_username` and the requirement's known repo info, eliminating manual URL entry for 12 of 15 requirements. Requires adding `required_repo` to 8 YAML requirements that lack it, a URL-builder helper, and template updates.

## Context
- `user.github_username` is already available in the phase page template context
- `requirement_card.html` shows a URL input where users manually type their GitHub URL
- 2 of 15 requirements already have `required_repo`; 8 more reference a known repo but lack the field
- 3 requirements (tokens, deployed API) are not GitHub URLs and are excluded

## Auto-URL mapping

| Requirement | Type | Auto URL | Deterministic? |
|---|---|---|---|
| github-profile | github_profile | `https://github.com/{username}` | Full |
| profile-readme | profile_readme | `https://github.com/{username}/{username}` | Full |
| linux-ctfs-fork | repo_fork | `https://github.com/{username}/linux-ctfs` | Full |
| networking-lab-fork | repo_fork | `https://github.com/{username}/networking-lab` | Full |
| journal-pr-* (5) | pr_review | `https://github.com/{username}/journal-starter/pull/` | Partial (need PR #) |
| journal-api-implementation | code_analysis | `https://github.com/{username}/journal-starter` | Full |
| devops-implementation | devops_analysis | `https://github.com/{username}/journal-starter` | Full |
| security-scanning | security_scanning | `https://github.com/{username}/journal-starter` | Full |

Excluded: `ctf_token`, `networking_token` (not URLs), `deployed_api` (not GitHub URL)

## Steps

### Phase A: Content updates (YAML)

1. Add `required_repo: learntocloud/journal-starter` to 8 requirements in YAML:
   - `content/phases/phase3/_phase.yaml`: journal-pr-logging, journal-pr-get-entry, journal-pr-delete-entry, journal-pr-ai-analysis, journal-pr-cloud-cli, journal-api-implementation
   - `content/phases/phase5/_phase.yaml`: devops-implementation
   - `content/phases/phase6/_phase.yaml`: security-scanning

### Phase B: URL builder helper

2. Create `build_auto_url(requirement: HandsOnRequirement, github_username: str) -> str | None` in `api/rendering/` (or as a utility function):
   - `github_profile` → `https://github.com/{username}`
   - `profile_readme` → `https://github.com/{username}/{username}`
   - `repo_fork` / `code_analysis` / `devops_analysis` / `security_scanning` → `https://github.com/{username}/{required_repo.split('/')[1]}` (requires `required_repo`)
   - `pr_review` → `https://github.com/{username}/{required_repo.split('/')[1]}/pull/` (partial, user appends PR#)
   - All others → `None`

### Phase C: Thread auto URLs into template context

3. In `api/routes/pages_routes.py` `phase_page()` route (line ~99): After building requirements list, compute `auto_urls_by_req = {req.id: build_auto_url(req, user.github_username) for req in requirements}` (guard on `user` and `github_username` being present). Pass to template context.

4. In `api/templates/pages/phase.html` (~line 83): Add `auto_url=auto_urls_by_req.get(req.id, '')` to the `{% with %}` block for `requirement_card.html`.

5. In `api/routes/htmx_routes.py` `htmx_submit_verification()` (line ~187): When re-rendering `requirement_card.html` on error/resubmission via `_render_card()`, also compute and pass `auto_url` using `build_auto_url()` + `github_username`.

### Phase D: Template update

6. In `api/templates/partials/requirement_card.html` (~line 55): Change the URL input's `value` attribute from:
   ```
   value="{% if submission %}{{ submission.submitted_value }}{% endif %}"
   ```
   to:
   ```
   value="{% if submission %}{{ submission.submitted_value }}{% elif auto_url %}{{ auto_url }}{% endif %}"
   ```
   This pre-fills the field only when no prior submission exists.

### Phase E: Tests

7. Unit test `build_auto_url()` — test each submission type mapping, None returns for non-URL types, and edge cases (missing `required_repo`, empty username).

8. Verify existing tests still pass — auto-population changes the default value but doesn't affect backend validation logic.

## Relevant files
- `content/phases/phase3/_phase.yaml` — add `required_repo` to 6 requirements
- `content/phases/phase5/_phase.yaml` — add `required_repo` to 1 requirement
- `content/phases/phase6/_phase.yaml` — add `required_repo` to 1 requirement
- `api/schemas.py` — `HandsOnRequirement` schema (no changes needed, `required_repo` field already exists)
- `api/rendering/` — new or existing module for `build_auto_url()` helper
- `api/routes/pages_routes.py` — `phase_page()` route, `_template_context()` helper
- `api/routes/htmx_routes.py` — `htmx_submit_verification()`, `_render_card()` inner function
- `api/templates/pages/phase.html` — `{% with %}` block for requirement_card include
- `api/templates/partials/requirement_card.html` — URL input value attribute

## Verification
1. `uv run ruff check api/ && uv run ruff format --check api/` — lint/format
2. `uv run ty check api/` — type check
3. `uv run pytest api/tests/ -x` — existing tests pass
4. Manual: Navigate to each phase page while logged in, confirm URL inputs are pre-filled with correct GitHub URLs
5. Manual: Submit a verification — confirm the pre-filled URL is accepted
6. Manual: Check that token/deployed_api fields are NOT pre-filled

## Decisions
- **Pre-fill, not lock**: URL inputs remain editable. Users can override if needed. Backend validation (username match check) is the security gate.
- **Reuse `required_repo` field**: Rather than adding a new field, extend `required_repo` to non-fork requirements. Semantics: "the upstream repo this requirement references." No schema change needed since `required_repo: str | None` already exists on `HandsOnRequirement`.
- **Excluded**: `ctf_token`, `networking_token`, `deployed_api` — not GitHub URLs, no auto-population.
- **PR review partial fill**: For `pr_review`, the URL is filled up to `/pull/` — user appends the PR number. This is still a significant UX improvement.

## Further Considerations
1. **Read-only for fully deterministic URLs**: For `github_profile`, `profile_readme`, `repo_fork`, `code_analysis`, etc., the URL is fully computable. Making the input read-only would prevent injection entirely. Recommend as a follow-up UX enhancement.
2. **Helper placement**: `build_auto_url` could go in `api/rendering/` (if a rendering module for requirements exists) or as a standalone function in a new `api/rendering/verification.py`. Check what rendering modules exist.
