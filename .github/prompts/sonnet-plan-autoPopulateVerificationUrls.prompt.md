# Plan: Auto-populate Verification URLs (Issue #234)

**TL;DR**: Add a `url_template` field to each verification requirement in the YAML files and `HandsOnRequirement` schema. The template uses it with the logged-in user's `github_username` to pre-fill URL inputs on first load. No routes, services, or DB changes needed.

---

## Steps

### Phase 1 — Schema
1. Add `url_template: str | None = None` to `HandsOnRequirement` in `api/schemas.py` (after the `required_repo` field).

### Phase 2 — YAML content (parallel with Phase 1)
2. `content/phases/phase0/_phase.yaml` — `github-profile`: `"https://github.com/{username}"`
3. `content/phases/phase1/_phase.yaml`:
   - `profile-readme`: `"https://github.com/{username}/{username}"`
   - `linux-ctfs-fork`: `"https://github.com/{username}/linux-ctfs"`
   - `linux-ctfs-token`: skip (token, no URL pattern)
4. `content/phases/phase2/_phase.yaml` — `networking-lab-fork`: `"https://github.com/{username}/networking-lab"`
5. `content/phases/phase3/_phase.yaml`:
   - `journal-pr-logging` through `journal-pr-cloud-cli`: `".../journal-starter/pull/1"` through `.../pull/5`
   - `journal-api-implementation`: `"https://github.com/{username}/journal-starter"`
6. Phase 4: **skip** — `deployed_api` is a custom API host, not a GitHub URL
7. `content/phases/phase5/_phase.yaml` — `devops-implementation`: `"https://github.com/{username}/journal-starter"`
8. `content/phases/phase6/_phase.yaml` — `security-scanning`: `"https://github.com/{username}/journal-starter"`

### Phase 3 — Templates (depends on Phase 1 + 2)
9. `api/templates/pages/phase.html` — add `github_username=user.github_username if user else None` to the `{% with %}` block that includes `requirement_card.html`.
10. `api/templates/partials/requirement_card.html` — update the `type="url"` input `value` attribute with priority logic:
    - Prior submission → `submission.submitted_value`
    - `url_template` + `github_username` available → `{{ url_template | replace('{username}', github_username) }}`
    - Otherwise → empty

---

## Relevant Files
- `api/schemas.py` — add field to `HandsOnRequirement`
- `content/phases/phase{0,1,2,3,5,6}/_phase.yaml` — add `url_template` per requirement
- `api/templates/pages/phase.html` — pass `github_username`
- `api/templates/partials/requirement_card.html` — use `url_template` for pre-population

---

## Verification
1. Start API, log in with GitHub, visit Phase 0–6 and confirm inputs are pre-filled correctly
2. Confirm Phase 4 deployed-API field is **not** pre-populated
3. Confirm a prior successful submission's value still takes priority
4. Run `uv run prek run --all-files` — no lint or type errors

---

## Decisions / Scope Boundaries
- Token submissions (`ctf_token`, `networking_token`) have no URL pattern — intentionally skipped
- HTMX fragment responses always have a prior `submission` value, so no change needed in the HTMX rendering path
- No server-side validation of the submitted URL against `url_template` — existing validators already check URL format/ownership; stricter enforcement can be a follow-up
