"""Agent Framework adapters for verification grading."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from typing import Any

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_openai import OpenAIChatOptions
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from learn_to_cloud_shared.verification.tasks import LLMGradingDecision

VERIFICATION_GRADER_AGENT_NAME = "VerificationGrader"
_PROJECT_ENDPOINT_ENV = "FOUNDRY_PROJECT_ENDPOINT"
_MODEL_DEPLOYMENT_ENV = "FOUNDRY_MODEL_DEPLOYMENT_NAME"
_REQUIRED_GRADING_ENV = (_PROJECT_ENDPOINT_ENV, _MODEL_DEPLOYMENT_ENV)

_GRADER_INSTRUCTIONS = """
You are the Learn to Cloud verification grader.

Grade only the evidence provided in the request. Do not infer unstated files,
repository state, permissions, deployments, or user intent. Apply the rubric
exactly as written. Return only one JSON object with:
- passed: true only when the evidence satisfies the rubric.
- score: 0.0 to 1.0 based on rubric completeness.
- confidence: 0.0 to 1.0 based only on evidence sufficiency.
- feedback: concise learner-facing explanation.
- next_steps: concrete remediation when passed is false.
- failure_reason: stable snake_case reason when passed is false.
- evidence_refs: paths, URLs, task ids, or evidence ids used in the decision.
Do not wrap the JSON in Markdown or include explanatory text outside the JSON.
""".strip()

_GRADER_OPTIONS: OpenAIChatOptions[LLMGradingDecision] = {
    "response_format": LLMGradingDecision,
    "max_tokens": 2000,
    "reasoning": {"effort": "low"},
    "verbosity": "low",
    "tools": None,
}


def missing_grading_config() -> list[str]:
    """Return required grading env var names that are unset or blank.

    Reading env vars is not a transient operation, so callers can treat a
    non-empty result as a permanent configuration error and fail fast
    instead of retrying.
    """
    return [
        name for name in _REQUIRED_GRADING_ENV if not (os.getenv(name) or "").strip()
    ]


@dataclass(frozen=True)
class GradingConfig:
    """Foundry settings the verification grader needs."""

    project_endpoint: str
    model_deployment_name: str

    @classmethod
    def from_env(cls) -> GradingConfig:
        missing = missing_grading_config()
        if missing:
            raise RuntimeError(
                f"{', '.join(missing)} required for LLM verification grading"
            )
        return cls(
            project_endpoint=os.environ[_PROJECT_ENDPOINT_ENV].strip(),
            model_deployment_name=os.environ[_MODEL_DEPLOYMENT_ENV].strip(),
        )


def _credential() -> DefaultAzureCredential | ManagedIdentityCredential:
    if os.getenv("AZURE_FUNCTIONS_ENVIRONMENT") == "Development":
        return DefaultAzureCredential()

    client_id = os.getenv("AZURE_CLIENT_ID")
    if client_id:
        return ManagedIdentityCredential(client_id=client_id)
    return ManagedIdentityCredential()


@cache
def get_verification_grader() -> Agent[Any]:
    """Return the lazily-constructed Foundry-backed grading agent.

    Validates required config defensively: the orchestrator pre-checks it,
    but activities can run on a different worker, so this stays a guard.
    """
    config = GradingConfig.from_env()
    return Agent(
        client=FoundryChatClient(
            project_endpoint=config.project_endpoint,
            model=config.model_deployment_name,
            credential=_credential(),
        ),
        instructions=_GRADER_INSTRUCTIONS,
        id="verification-grader",
        name=VERIFICATION_GRADER_AGENT_NAME,
        description="Grades verification evidence against a rubric.",
    )


async def grade_evidence(message: str) -> LLMGradingDecision:
    """Grade one self-contained verification prompt."""
    response = await get_verification_grader().run(message, options=_GRADER_OPTIONS)
    value = response.value
    if isinstance(value, LLMGradingDecision):
        return value
    if isinstance(value, Mapping):
        return LLMGradingDecision.model_validate(value)
    text = response.text.strip()
    if not text:
        raise ValueError("VerificationGrader returned an empty grading decision")
    return LLMGradingDecision.model_validate_json(text)
