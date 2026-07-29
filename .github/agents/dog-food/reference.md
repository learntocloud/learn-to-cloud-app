# Dog Food QA Reference

Read only the section needed for the requested workflow.

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

## Submission requirements

| Phase | Requirement slug | Submission type | Needs Functions? | Input |
|-------|------------------|-----------------|------------------|-------|
| 1 | `profile-readme` | `profile_readme` | Yes | Auto-derived |
| 1 | `linux-ctfs-fork` | `repo_fork` | Yes | Auto-derived |
| 1 | `linux-ctfs-token` | `ctf_token` | Yes | User-provided token |
| 2 | `networking-lab-fork` | `repo_fork` | Yes | Auto-derived |
| 2 | `networking-lab-token` | `networking_token` | Yes | User-provided token |
| 3 | `journal-api-implementation` | `journal_api_verifier` | Yes | Auto-derived |
| 4 | `deployed-journal-api` | `deployed_api` | Yes | User-provided URL |
| 5 | `devops-implementation` | `devops_analysis` | Yes | Auto-derived |
| 6 | `security-scanning` | `security_scanning` | Yes | Auto-derived |
| 7 | `career-reflection` | `career_reflection` | Yes | Three user-provided answers |

Auto-derived values come from the authenticated GitHub user. For
`career_reflection`, fill every rendered textarea with a substantive answer of
at least 200 characters.

## Report template

```markdown
## Dog Food Report

**Workflow:** Basic QA / Phase X submission QA

### Health

| Service | Status | Evidence |
|---------|--------|----------|
| API | Passed/Failed | ... |
| Functions | Passed/Failed/Not needed | ... |

### Pages

| Page | Loaded | Console errors | Server log evidence | Issues |
|------|--------|----------------|---------------------|--------|
| ... | Yes/No | None / details | None / exception + frame | ... |

Fill "Server log evidence" from `/tmp/dogfood-api.log` for any page that did not
load cleanly. Use `None` only when the page passed, or when the log genuinely
contained nothing for that request (which is itself worth listing under Issues).

### Interactions

| Test | Result | Evidence |
|------|--------|----------|
| Dark mode | Passed/Failed/Not attempted | ... |
| Step toggle and restore | Passed/Failed/Not attempted | ... |

### Submission

| Field | Value |
|-------|-------|
| Phase | ... |
| Requirement | ... |
| Input type | ... |
| Result | Passed/Failed/Timed out |
| Message | ... |
| Server log evidence | None / API and Functions errors |

### Cleanup

API and Functions processes stopped: Yes/No

### Issues Found

Each issue: what you observed in the browser, the matching server-side error
(exception type and application frame), and the steps to reproduce.

1. ...
```
