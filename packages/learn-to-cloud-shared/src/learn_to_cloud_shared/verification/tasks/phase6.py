"""Phase 6 task definitions: security scanning verification.

The deterministic gate (``codeql_status``) proves CodeQL ran green on the
current ``main`` HEAD. The LLM rubric below does *not* re-check that a scan
ran; it grades the committed workflow's **quality** and confirms it targets
**Python**, so it stays non-redundant with the gate.
"""

from __future__ import annotations

from learn_to_cloud_shared.verification.tasks.base import (
    EvidencePolicy,
    LLMRubricGraderConfig,
    VerificationTask,
)

PHASE6_REQUIREMENT_SLUG = "security-scanning"
CODEQL_WORKFLOW_PATH = ".github/workflows/codeql.yml"
DEPENDABOT_CONFIG_PATHS = (".github/dependabot.yml", ".github/dependabot.yaml")

SECURITY_SCANNING_RUBRIC_TASK = VerificationTask(
    id="security-scanning-rubric",
    phase_id=6,
    requirement_slug=PHASE6_REQUIREMENT_SLUG,
    name="Security Scanning Rubric Review",
    criteria=[
        (
            "The CodeQL workflow MUST analyze Python: its languages / "
            "build-mode configuration must include python"
        ),
        (
            "The workflow SHOULD run on sensible triggers: push and "
            "pull_request to the default branch, plus a scheduled run"
        ),
        (
            "SHOULD use a deliberate query suite (for example "
            "security-extended) rather than relying only on defaults"
        ),
        (
            "SHOULD pin the github/codeql-action steps to a version "
            "(a tag or SHA), not float on an implicit latest"
        ),
        (
            "Dependabot configuration (version key and at least one updates "
            "entry) is a bonus for defense-in-depth, not required"
        ),
        (
            "MUST grade only the repository evidence provided and MUST NOT "
            "re-judge whether a scan ran or passed (a separate gate proves that)"
        ),
    ],
    evidence=EvidencePolicy(
        source="repo_files",
        path_patterns=[CODEQL_WORKFLOW_PATH, *DEPENDABOT_CONFIG_PATHS],
        max_files=3,
        max_total_bytes=75 * 1024,
    ),
    grader=LLMRubricGraderConfig(
        rubric_id="phase6-security-scanning-v2",
        prompt_version="2026-07-13",
        passing_score=0.75,
        model="gpt-5-mini",
    ),
)

PHASE6_LLM_TASKS = [SECURITY_SCANNING_RUBRIC_TASK]
