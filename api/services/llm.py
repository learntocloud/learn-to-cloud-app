"""Gemini LLM integration for knowledge question grading.

SCALABILITY:
- Semaphore limits concurrent requests to prevent API quota exhaustion
- Circuit breaker fails fast when Gemini is unavailable (5 failures -> 60s recovery)
- 30 second timeout prevents hung requests from blocking workers
"""

import asyncio
import json
import logging
from dataclasses import dataclass

from circuitbreaker import circuit
from google import genai
from google.genai import types

from core.config import get_settings
from core.telemetry import track_dependency

logger = logging.getLogger(__name__)

_client: genai.Client | None = None

# Rate limiting: simple semaphore to limit concurrent LLM requests
# Prevents overwhelming the API under high load
_MAX_CONCURRENT_LLM_REQUESTS = 10
_llm_semaphore: asyncio.Semaphore | None = None

# Timeout for LLM API calls (seconds)
_LLM_TIMEOUT_SECONDS = 30


class GeminiServiceUnavailable(Exception):
    """Raised when Gemini API is unavailable (circuit open)."""

    pass


def _get_llm_semaphore() -> asyncio.Semaphore:
    """Get or create the LLM rate limiting semaphore."""
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_LLM_REQUESTS)
    return _llm_semaphore


def get_gemini_client() -> genai.Client:
    """Get or create the Gemini client (lazy initialization)."""
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set")
        _client = genai.Client(api_key=settings.google_api_key)
    return _client


@dataclass
class GradeResult:
    """Result of grading a knowledge question answer."""

    is_passed: bool
    feedback: str
    confidence_score: float


@track_dependency("gemini_api", "LLM")
@circuit(
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=Exception,
    name="gemini_circuit",
)
async def grade_answer(
    question_prompt: str,
    expected_concepts: list[str],
    user_answer: str,
    topic_name: str,
) -> GradeResult:
    """Grade a user's answer to a knowledge question using Gemini.

    Args:
        question_prompt: The question that was asked
        expected_concepts: Key concepts/keywords the answer should demonstrate
        user_answer: The user's submitted answer
        topic_name: Name of the topic for context

    Returns:
        GradeResult with pass/fail status, feedback, and confidence score

    Raises:
        GeminiServiceUnavailable: When circuit breaker is open (too many failures)
        asyncio.TimeoutError: When API call exceeds 30 seconds

    CIRCUIT BREAKER: Opens after 5 consecutive failures, recovers after 60 seconds.
    """
    settings = get_settings()
    client = get_gemini_client()

    system_prompt = f"""You are a knowledgeable and encouraging instructor for \
a cloud computing learning platform called "Learn to Cloud".

Your task is to evaluate a student's answer to a knowledge question \
about {topic_name}.

EVALUATION CRITERIA:
1. The answer should demonstrate understanding of the core concepts
2. Technical accuracy is important but exact wording is not required
3. The answer should address the question being asked
4. Partial understanding can still pass if the core concept is grasped

EXPECTED CONCEPTS the answer should touch on:
{", ".join(expected_concepts)}

SCORING:
- PASS: Answer demonstrates understanding of the main concept(s)
- FAIL: Answer misses the core concept or is factually incorrect

RESPONSE FORMAT (strict JSON):
{{
    "passed": true/false,
    "confidence": 0.0-1.0,
    "feedback": "Brief encouraging feedback explaining what was good or what to improve"
}}

Be encouraging but honest. If they fail, give constructive guidance."""

    user_message = f"""QUESTION: {question_prompt}

STUDENT'S ANSWER: {user_answer}

Please evaluate this answer."""

    # Use semaphore to limit concurrent LLM requests and prevent API quota exhaustion
    semaphore = _get_llm_semaphore()
    async with semaphore:
        try:
            # Wrap API call with timeout to prevent hung requests
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=settings.gemini_model,
                    contents=user_message,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.3,
                        max_output_tokens=500,
                        response_mime_type="application/json",
                    ),
                ),
                timeout=_LLM_TIMEOUT_SECONDS,
            )

            response_text = response.text or "{}"
            result = json.loads(response_text)

            return GradeResult(
                is_passed=result.get("passed", False),
                feedback=result.get("feedback", "Unable to provide feedback."),
                confidence_score=result.get("confidence", 0.5),
            )

        except TimeoutError:
            logger.error(f"Gemini API call timed out after {_LLM_TIMEOUT_SECONDS}s")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {e}")
            return GradeResult(
                is_passed=False,
                feedback="We couldn't process your answer. Please try again.",
                confidence_score=0.0,
            )
        except Exception as e:
            logger.exception(f"Error calling Gemini API: {e}")
            raise
