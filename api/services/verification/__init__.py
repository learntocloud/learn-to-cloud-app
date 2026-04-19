"""Verification subsystem for hands-on learning requirements.

Submodules:
    dispatcher        — Central routing of submissions to verifiers
    requirements      — Phase requirement registry and gating logic
    events            — In-process event bus for async verification results
    github_profile    — GitHub profile/README/fork verification (Phases 0-1)
    pull_request      — PR merge verification (Phase 3)
    ci_status         — CI test-pass verification (Phase 3)
    indicator_engine  — Deterministic indicator matching for PR diffs
    token_base        — HMAC token verification for CTF + Networking Lab
    devops_analysis   — DevOps artifact analysis (Phase 5)
    security_scanning — Dependabot + CodeQL verification (Phase 6)
    deployed_api      — Live API challenge-response testing (Phase 4)
    repo_utils        — Shared GitHub URL parsing and validation
    tasks/            — Task definitions per phase
"""
