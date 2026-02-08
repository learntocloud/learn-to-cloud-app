"""Journal API verification for Phase 2 hands-on validation.

This module validates that users have successfully implemented their Journal API
by verifying a pasted JSON response from GET /entries.

The response must:
- Be valid JSON (array format)
- Contain at least one entry
- Have entries with required fields: id, work, struggle, intention, created_at
- Have valid field types and constraints
"""

import json
import logging
import re
from datetime import datetime

from schemas import ValidationResult

logger = logging.getLogger(__name__)

# UUID v4 pattern (standard format from Python's uuid module)
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Required fields for a journal entry
_REQUIRED_FIELDS = {"id", "work", "struggle", "intention", "created_at"}

# String fields with max length constraint (256 chars per journal-starter schema)
_STRING_FIELDS_WITH_LIMIT = {"work", "struggle", "intention"}
_MAX_STRING_LENGTH = 256


def _validate_uuid(value: str) -> bool:
    """Check if a string is a valid UUID v4."""
    return bool(_UUID_PATTERN.match(value))


def _validate_datetime(value: str) -> bool:
    """Check if a string is a valid ISO 8601 datetime."""
    try:
        # Handle common datetime formats from FastAPI/Pydantic
        # ISO format: 2025-01-25T10:30:00Z or 2025-01-25T10:30:00+00:00
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        datetime.fromisoformat(value)
        return True
    except (ValueError, TypeError):
        return False


def _validate_entry(entry: dict, index: int) -> tuple[bool, str | None]:
    """Validate a single journal entry.

    Args:
        entry: The entry dict to validate
        index: The index of this entry in the array (for error messages)

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check required fields
    missing_fields = _REQUIRED_FIELDS - set(entry.keys())
    if missing_fields:
        return (
            False,
            f"Entry {index + 1} missing fields: {', '.join(sorted(missing_fields))}",
        )

    # Validate id is a UUID
    if not isinstance(entry.get("id"), str) or not _validate_uuid(entry["id"]):
        return False, f"Entry {index + 1} has invalid id (expected UUID format)"

    # Validate string fields
    for field in _STRING_FIELDS_WITH_LIMIT:
        value = entry.get(field)
        if not isinstance(value, str):
            return False, f"Entry {index + 1} field '{field}' must be a string"
        if len(value) > _MAX_STRING_LENGTH:
            msg = f"Entry {index + 1} field '{field}' exceeds max length"
            return False, msg
        if not value.strip():
            return False, f"Entry {index + 1} field '{field}' cannot be empty"

    # Validate created_at is a datetime
    created_at = entry.get("created_at")
    if not isinstance(created_at, str) or not _validate_datetime(created_at):
        return (
            False,
            f"Entry {index + 1} has invalid created_at (expected ISO 8601 datetime)",
        )

    # updated_at is optional but if present, must be valid datetime
    updated_at = entry.get("updated_at")
    if updated_at is not None:
        if not isinstance(updated_at, str) or not _validate_datetime(updated_at):
            return False, f"Entry {index + 1} has invalid updated_at"

    return True, None


def validate_journal_api_response(json_response: str) -> ValidationResult:
    """Validate a pasted JSON response from GET /entries.

    Args:
        json_response: The raw JSON string pasted by the user

    Returns:
        ValidationResult with validation status and feedback
    """
    json_response = json_response.strip()

    if not json_response:
        return ValidationResult(
            is_valid=False,
            message="Please paste your JSON response from GET /entries",
        )

    # Parse JSON
    try:
        data = json.loads(json_response)
    except json.JSONDecodeError:
        return ValidationResult(
            is_valid=False,
            message="Invalid JSON format. Make sure you copied the complete response.",
        )

    # Must be an array
    if not isinstance(data, list):
        return ValidationResult(
            is_valid=False,
            message="Response must be an array of entries.",
        )

    # Must have at least one entry
    if len(data) == 0:
        return ValidationResult(
            is_valid=False,
            message="No entries found. Create an entry with POST /entries first.",
        )

    # Validate each entry
    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            return ValidationResult(
                is_valid=False,
                message=f"Entry {i + 1} is not a valid object.",
            )

        is_valid, error = _validate_entry(entry, i)
        if not is_valid:
            return ValidationResult(
                is_valid=False,
                message=error or "Entry validation failed",
            )

    count = len(data)
    entry_word = "entry" if count == 1 else "entries"
    return ValidationResult(
        is_valid=True,
        message=f"Journal API verified! Found {count} valid {entry_word}.",
    )
