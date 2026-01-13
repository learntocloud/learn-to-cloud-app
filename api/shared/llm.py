"""Gemini LLM integration for knowledge question grading."""

import json
import logging
from dataclasses import dataclass

from google import genai
from google.genai import types

from .config import get_settings

logger = logging.getLogger(__name__)

# Lazy-initialized client
_client: genai.Client | None = None


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

    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.3,
                max_output_tokens=500,
                response_mime_type="application/json",
            ),
        )

        # Parse the JSON response
        response_text = response.text or "{}"
        result = json.loads(response_text)

        return GradeResult(
            is_passed=result.get("passed", False),
            feedback=result.get("feedback", "Unable to provide feedback."),
            confidence_score=result.get("confidence", 0.5),
        )

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
