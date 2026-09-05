# Dog Food QA Reference

Read only the section you need. The page tables are a **coverage backstop**, not
a checklist: pursue the user's goal first, then use these to make sure a run
touched the main surface. "Expected evidence" is the minimum that proves a page
rendered, not the full definition of working.

## Public pages

| Page | URL |
|------|-----|
| Home | `http://localhost:8000/` |
| Curriculum | `http://localhost:8000/curriculum` |
| FAQ | `http://localhost:8000/faq` |
| Privacy | `http://localhost:8000/privacy` |
| Terms | `http://localhost:8000/terms` |

## Authenticated pages

| Page | URL | Expected evidence |
|------|-----|-------------------|
| Dashboard | `/dashboard` | Navigation, main content, username |
| Account | `/account` | Navigation, main content, account settings |
| Phase 0 | `/phase/0` | Navigation, main content, no server error |
| Phase 1 | `/phase/1` | Navigation, main content, topic links |
| Phase 2 | `/phase/2` | Navigation, main content, no server error |
| Phase 3 | `/phase/3` | Navigation, main content, no server error |
| Phase 4 | `/phase/4` | Navigation, main content, no server error |
| Phase 5 | `/phase/5` | Navigation, main content, no server error |
| Phase 6 | `/phase/6` | Navigation, main content, no server error |
| Phase 7 | `/phase/7` | Navigation, main content, no server error |
| First topic | First `/phase/1/*` link | Learning steps and checkboxes |

## Authentication response contract

Use these expectations when the learner's goal involves signing in, session
expiry, or signing out. They are not all product defects merely because an
HTTP request was rejected.

| Situation | Expected behavior |
|-----------|-------------------|
| Anonymous user opens a protected page | 303 to `/auth/login`; subsequent login navigation uses GET |
| Anonymous API request | 401 without a login redirect |
| HTMX action with a missing or expired session | 401; the existing browser handler navigates to login |
| HTMX endpoint called without the HTMX header | Still 401, not a login redirect |
| Logout with a valid, missing, or rejected cookie | Session/cookie cleared, 303 to `/`; safe to repeat |
| Public page without a session | Remains available |

A fresh, valid local session unexpectedly rejected by a protected route is a
defect. Normal expired-session navigation is not; report friction if it is
confusing or leaves the learner stuck.

Logout clears this browser's cookie, not every copy of an issued signed cookie.
Do not report missing global revocation as a new regression; it is tracked in
[#828](https://github.com/learntocloud/learn-to-cloud-app/issues/828). Do report
new behavior that differs from the documented response contract.

See [Authentication and sessions](../../../docs/contributing.md#authentication-and-sessions)
for the underlying design. Record sanitized routes, statuses, and visible
outcomes, never cookies, tokens, or user identities.

## Submission requirements

Source of truth is `packages/learn-to-cloud-shared/src/learn_to_cloud_shared/content/curriculum.json`
(`phases[].hands_on_verification.requirements`). If a slug here does not match a
requirement card in the app, trust the artifact and report the drift.

| Phase | Requirement slug | Submission type | Needs Functions? | Input |
|-------|------------------|-----------------|------------------|-------|
| 0 | `profile-readme` | `profile_readme` | Yes | Auto-derived |
| 1 | `linux-ctfs-fork` | `repo_fork` | Yes | Auto-derived |
| 1 | `linux-ctfs-token` | `ctf_token` | Yes | Minted locally (see below) |
| 2 | `networking-lab-fork` | `repo_fork` | Yes | Auto-derived |
| 2 | `networking-lab-token` | `networking_token` | Yes | Minted locally (see below) |
| 3 | `journal-api-implementation` | `journal_api_verifier` | Yes | Auto-derived |
| 4 | `deployed-journal-api` | `deployed_api` | Yes | User-provided URL |
| 5 | `devops-implementation` | `devops_analysis` | Yes | Auto-derived |
| 6 | `security-scanning` | `security_scanning` | Yes | Auto-derived |
| 7 | `career-reflection` | `career_reflection` | Yes | Three answers, 200 characters minimum each |

Auto-derived values come from the authenticated GitHub user, and the field is
rendered read-only. If a prefilled repository is not the one you were asked to
test, report it rather than trying to force the value.

Lab tokens (`ctf_token`, `networking_token`) are minted locally with
`scripts/mint_lab_token.py`; no real lab completion is required. The token
carries the exact challenge count the verifier expects (18 for the CTF, 4 for
the networking lab) and is bound to the GitHub username you are signed in as.

For `career_reflection`, fill every rendered textarea with a substantive answer.

## Report template

Lead with findings. The tables exist so the reader knows what was covered; they
are not the point of the report.

````markdown
## Dog Food Report

**Goal:** what you set out to do
**Verdict:** one sentence — did the goal succeed, partially succeed, or fail

### Defects

Objective breakage. For each: what you did, what you saw, the server-side
evidence (exception type and application frame), and how to reproduce.

1. ...

### Friction

Things that worked but shouldn't ship as-is: dead-looking controls, messages
that don't say what to do next, flows that made you guess.

1. ...

### Coverage

| Area | Exercised | Result |
|------|-----------|--------|
| Public pages | which ones | clean / see defect N |
| Authenticated pages | which ones | clean / see defect N |
| Interactions | dark mode, step toggle, ... | clean / see defect N |
| Submission | phase + requirement | passed / failed / timed out |

**Not exercised:** everything you did not reach, and why.

### Environment

| Item | Value |
|------|-------|
| API | healthy / failed, PID |
| Functions | healthy / not needed / failed, PID |
| Processes stopped | Yes/No |
| Logs | `/tmp/dogfood-api.log`, `/tmp/dogfood-functions.log` |
````

This report is evidence of what was found, not proof the app is healthy.
