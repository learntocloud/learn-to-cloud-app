"""Verification subsystem for hands-on learning requirements.

This package contains all verification logic: the central dispatcher,
phase-specific verifiers (GitHub, CTF, LLM-based code/devops analysis,
security scanning, deployed API testing), shared base modules, and
task definitions.

Submodules:
    dispatcher      — Central routing of submissions to verifiers
    requirements    — Phase requirement registry and gating logic
    events          — In-process event bus for async verification results
    github_profile  — GitHub profile/README/fork verification (Phases 0-1)
    pull_request    — PR merge verification (Phase 3)
    ci_status       — CI test-pass verification (Phase 3)
    token_base      — HMAC token verification for CTF + Networking Lab
    devops_analysis — LLM-powered DevOps artifact analysis (Phase 5)
    security_scanning — Dependabot + CodeQL verification (Phase 6)
    deployed_api    — Live API challenge-response testing (Phase 4)
    llm_base        — Shared LLM orchestration utilities
    tasks/          — Task definitions and grading schemas per phase
"""
