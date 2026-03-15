"""Phase 3 task definitions: Journal API code analysis.

Defines the 5 tasks learners must implement in their journal-starter fork,
plus the Pydantic models used for structured LLM output.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field


class TaskDefinition(TypedDict, total=False):
    """Type definition for a Phase 3 verification task."""

    id: str
    name: str
    file: str
    files: list[str]
    criteria: list[str]
    starter_code_hint: str
    pass_indicators: list[str]
    fail_indicators: list[str]


# Allowlist of files that can be fetched — prevents path traversal attacks
ALLOWED_FILE_PATHS: frozenset[str] = frozenset(
    [
        "api/main.py",
        "api/routers/journal_router.py",
        "api/services/llm_service.py",
        ".devcontainer/devcontainer.json",
    ]
)

# Maximum file size to prevent token exhaustion (50KB)
MAX_FILE_SIZE_BYTES: int = 50 * 1024


PHASE3_TASKS: list[TaskDefinition] = [
    {
        "id": "logging-setup",
        "name": "Logging Setup",
        "file": "api/main.py",
        "criteria": [
            "MUST have `import logging` or `import structlog` statement",
            "MUST call logging.basicConfig() or configure structlog",
            "MUST set log level (INFO, DEBUG, or WARNING)",
            "SHOULD have at least one logger.info() or logger.debug() call",
        ],
        "starter_code_hint": (
            "Starter code has only: `from dotenv import load_dotenv` and "
            "`from fastapi import FastAPI`. Look for added logging imports."
        ),
        "pass_indicators": [
            "import logging",
            "import structlog",
            "logging.basicConfig",
            "logging.getLogger",
            "structlog.configure",
        ],
        "fail_indicators": [
            "# TODO: Setup basic console logging",
            "# Hint: Use logging.basicConfig()",
        ],
    },
    {
        "id": "get-single-entry",
        "name": "GET Single Entry Endpoint",
        "file": "api/routers/journal_router.py",
        "criteria": [
            "MUST NOT raise HTTPException(status_code=501) - that's the starter stub",
            "MUST call entry_service.get_entry(entry_id)",
            "MUST raise HTTPException(status_code=404) when entry is None",
            "MUST return the entry object (not wrapped in a dict)",
        ],
        "starter_code_hint": (
            "Starter code raises `HTTPException(status_code=501, "
            'detail="Not implemented - complete this endpoint!")`. '
            "If this line is still present, the task is NOT complete."
        ),
        "pass_indicators": [
            "entry_service.get_entry",
            "status_code=404",
            "HTTPException",
        ],
        "fail_indicators": [
            'detail="Not implemented - complete this endpoint!"',
        ],
    },
    {
        "id": "delete-entry",
        "name": "DELETE Entry Endpoint",
        "file": "api/routers/journal_router.py",
        "criteria": [
            "MUST NOT raise HTTPException(status_code=501) - that's the starter stub",
            "MUST check if entry exists before deleting",
            "MUST raise HTTPException(status_code=404) when entry not found",
            "MUST call entry_service.delete_entry(entry_id)",
            "SHOULD return status 200 or 204 on success",
        ],
        "starter_code_hint": (
            "Starter code raises `HTTPException(status_code=501)`. "
            "A complete implementation will have get_entry() check, "
            "delete_entry() call, and 404 handling."
        ),
        "pass_indicators": [
            "entry_service.delete_entry",
            "entry_service.get_entry",
            "status_code=404",
        ],
        "fail_indicators": [
            'detail="Not implemented - complete this endpoint!"',
        ],
    },
    {
        "id": "ai-analysis",
        "name": "AI-Powered Entry Analysis",
        "files": ["api/services/llm_service.py", "api/routers/journal_router.py"],
        "criteria": [
            "llm_service.py: MUST NOT raise NotImplementedError - that's the stub",
            "llm_service.py: MUST import an LLM SDK (openai, anthropic, boto3, etc.)",
            "llm_service.py: MUST make an API call to an LLM provider",
            "llm_service.py: MUST return dict with sentiment, summary, topics keys",
            "journal_router.py: analyze_entry() MUST NOT raise HTTPException(501)",
            "journal_router.py: MUST call llm_service.analyze_journal_entry()",
        ],
        "starter_code_hint": (
            "llm_service.py starter raises `NotImplementedError(...)`. "
            "journal_router.py analyze_entry() raises HTTPException(501). "
            "Both must be replaced with working implementations."
        ),
        "pass_indicators": [
            "from openai",
            "import openai",
            "import anthropic",
            "import boto3",
            "from google",
            "analyze_journal_entry",
            "sentiment",
            "summary",
            "topics",
        ],
        "fail_indicators": [
            "Implement this function using your chosen LLM API",
            "See the Learn to Cloud curriculum for guidance.",
            'detail="Implement this endpoint - see Learn to Cloud curriculum"',
        ],
    },
    {
        "id": "cloud-cli-setup",
        "name": "Cloud CLI Setup",
        "file": ".devcontainer/devcontainer.json",
        "criteria": [
            "At least ONE of these lines MUST be uncommented:",
            '  - "ghcr.io/devcontainers/features/azure-cli:1": {}',
            '  - "ghcr.io/devcontainers/features/aws-cli:1": {}',
            '  - "ghcr.io/devcontainers/features/gcloud:1": {}',
        ],
        "starter_code_hint": (
            "Starter has all three CLI features commented out with `//`. "
            "Look for lines WITHOUT the leading `//` comment."
        ),
        "pass_indicators": [
            '"ghcr.io/devcontainers/features/azure-cli:1"',
            '"ghcr.io/devcontainers/features/aws-cli:1"',
            '"ghcr.io/devcontainers/features/gcloud:1"',
        ],
        "fail_indicators": [
            '// "ghcr.io/devcontainers/features/azure-cli:1"',
            '// "ghcr.io/devcontainers/features/aws-cli:1"',
            '// "ghcr.io/devcontainers/features/gcloud:1"',
        ],
    },
]


# Valid task IDs as a Literal type for structured output validation
_VALID_TASK_IDS = Literal[
    "logging-setup",
    "get-single-entry",
    "delete-entry",
    "ai-analysis",
    "cloud-cli-setup",
]


class TaskGrade(BaseModel):
    """Structured output model for a single task grade from the LLM."""

    model_config = ConfigDict(extra="forbid")

    task_id: _VALID_TASK_IDS = Field(description="The task identifier")
    passed: bool = Field(description="Whether the task implementation is complete")
    feedback: str = Field(
        description="1-3 sentences of specific, educational feedback",
        max_length=500,
    )


class CodeAnalysisResponse(BaseModel):
    """Structured output model for the full code analysis LLM response."""

    model_config = ConfigDict(extra="forbid")

    tasks: list[TaskGrade] = Field(
        description="Grading results for all 5 tasks",
        min_length=5,
        max_length=5,
    )
