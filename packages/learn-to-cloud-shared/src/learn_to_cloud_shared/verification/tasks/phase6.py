"""Phase 6 task definitions: security scanning verification."""

from __future__ import annotations

from learn_to_cloud_shared.verification.tasks.base import (
    EvidencePolicy,
    FilePresenceGraderConfig,
    LLMRubricGraderConfig,
    VerificationTask,
)

PHASE6_REQUIREMENT_ID = "security-scanning"
CODEQL_ACTION_PATTERN = "github/codeql-action"
DEPENDABOT_CONFIG_PATHS = (".github/dependabot.yml", ".github/dependabot.yaml")

DEPENDABOT_TASK = VerificationTask(
    id="dependabot",
    phase_id=6,
    requirement_id=PHASE6_REQUIREMENT_ID,
    name="Dependabot Configuration",
    criteria=[
        "MUST include a .github/dependabot.yml or .github/dependabot.yaml file",
        "MUST include a version key",
        "MUST include at least one updates entry",
    ],
    evidence=EvidencePolicy(
        source="repo_files",
        path_patterns=list(DEPENDABOT_CONFIG_PATHS),
        max_files=1,
    ),
    grader=FilePresenceGraderConfig(
        required_any=list(DEPENDABOT_CONFIG_PATHS),
        content_indicators=["version", "updates"],
    ),
)

CODEQL_TASK = VerificationTask(
    id="codeql",
    phase_id=6,
    requirement_id=PHASE6_REQUIREMENT_ID,
    name="CodeQL Scanning",
    criteria=[
        "MUST include a GitHub Actions workflow for CodeQL",
        "MUST use the github/codeql-action action",
    ],
    evidence=EvidencePolicy(
        source="repo_files",
        path_patterns=[".github/workflows/"],
        max_files=5,
    ),
    grader=FilePresenceGraderConfig(
        required_any=[".github/workflows/"],
        content_indicators=[CODEQL_ACTION_PATTERN],
    ),
)

SECURITY_SCANNING_RUBRIC_TASK = VerificationTask(
    id="security-scanning-rubric",
    phase_id=6,
    requirement_id=PHASE6_REQUIREMENT_ID,
    name="Security Scanning Rubric Review",
    criteria=[
        "MUST show valid Dependabot configuration or CodeQL scanning evidence",
        "Dependabot evidence MUST include a version key and at least one updates entry",
        "CodeQL evidence MUST include a workflow using github/codeql-action",
        (
            "MUST grade only the repository evidence and deterministic task "
            "results provided"
        ),
    ],
    evidence=EvidencePolicy(
        source="repo_files",
        path_patterns=[*DEPENDABOT_CONFIG_PATHS, ".github/workflows/"],
        max_files=6,
        max_total_bytes=75 * 1024,
    ),
    grader=LLMRubricGraderConfig(
        rubric_id="phase6-security-scanning-v1",
        prompt_version="2026-05-08",
        passing_score=0.75,
        model="gpt-5-mini",
    ),
)

PHASE6_TASKS = [DEPENDABOT_TASK, CODEQL_TASK]
PHASE6_LLM_TASKS = [SECURITY_SCANNING_RUBRIC_TASK]
