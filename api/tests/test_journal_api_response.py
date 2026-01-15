"""Tests for Journal API response validation.

Tests the validate_journal_api_response function that verifies
learners have a working Journal API by validating their GET /entries response.

Based on the journal-starter Entry model:
- id: UUID string
- work: str (max 256)
- struggle: str (max 256)
- intention: str (max 256)
- created_at: datetime
- updated_at: datetime (optional)
"""

import json
from datetime import UTC, datetime
from uuid import uuid4

from services.hands_on_verification import validate_journal_api_response


class TestValidJournalResponses:
    """Tests for valid Journal API responses."""

    def test_single_entry_valid(self):
        """A single valid entry should pass validation."""
        response = json.dumps(
            [
                {
                    "id": str(uuid4()),
                    "work": "Learned FastAPI basics",
                    "struggle": "Understanding async/await",
                    "intention": "Build the POST endpoint tomorrow",
                    "created_at": datetime.now(UTC).isoformat(),
                }
            ]
        )
        result = validate_journal_api_response(response)
        assert result.is_valid is True
        assert "1 entry" in result.message

    def test_multiple_entries_valid(self):
        """Multiple valid entries should pass validation."""
        response = json.dumps(
            [
                {
                    "id": str(uuid4()),
                    "work": "Day 1 work",
                    "struggle": "Day 1 struggle",
                    "intention": "Day 1 intention",
                    "created_at": "2025-01-14T10:00:00Z",
                },
                {
                    "id": str(uuid4()),
                    "work": "Day 2 work",
                    "struggle": "Day 2 struggle",
                    "intention": "Day 2 intention",
                    "created_at": "2025-01-15T10:00:00Z",
                },
                {
                    "id": str(uuid4()),
                    "work": "Day 3 work",
                    "struggle": "Day 3 struggle",
                    "intention": "Day 3 intention",
                    "created_at": "2025-01-16T10:00:00Z",
                },
            ]
        )
        result = validate_journal_api_response(response)
        assert result.is_valid is True
        assert "3 entries" in result.message

    def test_entry_with_updated_at_field(self):
        """Entry with optional updated_at field should pass."""
        response = json.dumps(
            [
                {
                    "id": str(uuid4()),
                    "work": "Working on APIs",
                    "struggle": "Database connections",
                    "intention": "Deploy to cloud",
                    "created_at": "2025-01-14T10:00:00Z",
                    "updated_at": "2025-01-14T12:00:00Z",
                }
            ]
        )
        result = validate_journal_api_response(response)
        assert result.is_valid is True

    def test_entry_with_extra_fields(self):
        """Entry with extra fields should still pass (forward compatibility)."""
        response = json.dumps(
            [
                {
                    "id": str(uuid4()),
                    "work": "Working on APIs",
                    "struggle": "Database connections",
                    "intention": "Deploy to cloud",
                    "created_at": "2025-01-14T10:00:00Z",
                    "custom_field": "some value",
                    "another_field": 123,
                }
            ]
        )
        result = validate_journal_api_response(response)
        assert result.is_valid is True

    def test_uuid_formats(self):
        """Various valid UUID formats should pass."""
        # Standard lowercase
        response1 = json.dumps(
            [
                {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "work": "test",
                    "struggle": "test",
                    "intention": "test",
                    "created_at": "2025-01-14T10:00:00Z",
                }
            ]
        )
        assert validate_journal_api_response(response1).is_valid is True

        # Uppercase (should also be valid)
        response2 = json.dumps(
            [
                {
                    "id": "123E4567-E89B-12D3-A456-426614174000",
                    "work": "test",
                    "struggle": "test",
                    "intention": "test",
                    "created_at": "2025-01-14T10:00:00Z",
                }
            ]
        )
        assert validate_journal_api_response(response2).is_valid is True

    def test_whitespace_in_response(self):
        """Response with leading/trailing whitespace should pass."""
        response = """
        [{"id": "123e4567-e89b-12d3-a456-426614174000",
          "work": "test", "struggle": "test", "intention": "test",
          "created_at": "2025-01-14T10:00:00Z"}]
        """
        result = validate_journal_api_response(response)
        assert result.is_valid is True


class TestInvalidJournalResponses:
    """Tests for invalid Journal API responses."""

    def test_empty_string(self):
        """Empty string should fail."""
        result = validate_journal_api_response("")
        assert result.is_valid is False
        assert "paste" in result.message.lower()

    def test_whitespace_only(self):
        """Whitespace-only string should fail."""
        result = validate_journal_api_response("   \n\t  ")
        assert result.is_valid is False

    def test_invalid_json(self):
        """Invalid JSON should fail with helpful message."""
        result = validate_journal_api_response("not json at all")
        assert result.is_valid is False
        assert "Invalid JSON" in result.message

    def test_truncated_json(self):
        """Truncated JSON should fail."""
        result = validate_journal_api_response('[{"id": "123e4567-e89b-12d3-a456-')
        assert result.is_valid is False
        assert "Invalid JSON" in result.message

    def test_json_object_without_entries_key(self):
        """Object without 'entries' key should fail."""
        response = json.dumps({"data": [{"id": str(uuid4())}], "count": 1})
        result = validate_journal_api_response(response)
        assert result.is_valid is False
        assert "entries" in result.message.lower() or "array" in result.message.lower()

    def test_empty_array(self):
        """Empty array should fail - need at least one entry."""
        result = validate_journal_api_response("[]")
        assert result.is_valid is False
        assert "No entries found" in result.message
        assert "POST /entries" in result.message

    def test_empty_entries_in_wrapped_format(self):
        """Empty entries array in wrapped format should fail."""
        response = json.dumps({"entries": [], "count": 0})
        result = validate_journal_api_response(response)
        assert result.is_valid is False
        assert "No entries found" in result.message

    def test_array_of_non_objects(self):
        """Array of non-objects should fail."""
        result = validate_journal_api_response('["string1", "string2"]')
        assert result.is_valid is False
        assert "not a valid object" in result.message


class TestMissingFields:
    """Tests for entries with missing required fields."""

    def test_missing_id(self):
        """Entry missing 'id' should fail."""
        response = json.dumps(
            [
                {
                    "work": "test",
                    "struggle": "test",
                    "intention": "test",
                    "created_at": "2025-01-14T10:00:00Z",
                }
            ]
        )
        result = validate_journal_api_response(response)
        assert result.is_valid is False
        assert "missing required fields" in result.message
        assert "id" in result.message

    def test_missing_work(self):
        """Entry missing 'work' should fail."""
        response = json.dumps(
            [
                {
                    "id": str(uuid4()),
                    "struggle": "test",
                    "intention": "test",
                    "created_at": "2025-01-14T10:00:00Z",
                }
            ]
        )
        result = validate_journal_api_response(response)
        assert result.is_valid is False
        assert "work" in result.message

    def test_missing_struggle(self):
        """Entry missing 'struggle' should fail."""
        response = json.dumps(
            [
                {
                    "id": str(uuid4()),
                    "work": "test",
                    "intention": "test",
                    "created_at": "2025-01-14T10:00:00Z",
                }
            ]
        )
        result = validate_journal_api_response(response)
        assert result.is_valid is False
        assert "struggle" in result.message

    def test_missing_intention(self):
        """Entry missing 'intention' should fail."""
        response = json.dumps(
            [
                {
                    "id": str(uuid4()),
                    "work": "test",
                    "struggle": "test",
                    "created_at": "2025-01-14T10:00:00Z",
                }
            ]
        )
        result = validate_journal_api_response(response)
        assert result.is_valid is False
        assert "intention" in result.message

    def test_missing_created_at(self):
        """Entry missing 'created_at' should fail."""
        response = json.dumps(
            [
                {
                    "id": str(uuid4()),
                    "work": "test",
                    "struggle": "test",
                    "intention": "test",
                }
            ]
        )
        result = validate_journal_api_response(response)
        assert result.is_valid is False
        assert "created_at" in result.message

    def test_missing_multiple_fields(self):
        """Entry missing multiple fields should list all missing."""
        response = json.dumps(
            [
                {
                    "id": str(uuid4()),
                    "work": "test",
                }
            ]
        )
        result = validate_journal_api_response(response)
        assert result.is_valid is False
        assert "struggle" in result.message
        assert "intention" in result.message
        assert "created_at" in result.message

    def test_second_entry_missing_fields(self):
        """Second entry with missing fields should fail with correct index."""
        response = json.dumps(
            [
                {
                    "id": str(uuid4()),
                    "work": "test",
                    "struggle": "test",
                    "intention": "test",
                    "created_at": "2025-01-14T10:00:00Z",
                },
                {
                    "id": str(uuid4()),
                    "work": "test",
                    # Missing struggle, intention, created_at
                },
            ]
        )
        result = validate_journal_api_response(response)
        assert result.is_valid is False
        assert "Entry 2" in result.message


class TestInvalidFieldValues:
    """Tests for entries with invalid field values."""

    def test_invalid_uuid_format(self):
        """Entry with invalid UUID format should fail."""
        response = json.dumps(
            [
                {
                    "id": "not-a-valid-uuid",
                    "work": "test",
                    "struggle": "test",
                    "intention": "test",
                    "created_at": "2025-01-14T10:00:00Z",
                }
            ]
        )
        result = validate_journal_api_response(response)
        assert result.is_valid is False
        assert "invalid ID format" in result.message
        assert "UUID" in result.message

    def test_numeric_id(self):
        """Numeric ID (not UUID) should fail."""
        response = json.dumps(
            [
                {
                    "id": 12345,
                    "work": "test",
                    "struggle": "test",
                    "intention": "test",
                    "created_at": "2025-01-14T10:00:00Z",
                }
            ]
        )
        result = validate_journal_api_response(response)
        assert result.is_valid is False
        assert "invalid ID format" in result.message

    def test_empty_work_field(self):
        """Empty 'work' field should fail."""
        response = json.dumps(
            [
                {
                    "id": str(uuid4()),
                    "work": "",
                    "struggle": "test",
                    "intention": "test",
                    "created_at": "2025-01-14T10:00:00Z",
                }
            ]
        )
        result = validate_journal_api_response(response)
        assert result.is_valid is False
        assert "empty" in result.message.lower()
        assert "work" in result.message

    def test_whitespace_only_field(self):
        """Whitespace-only field should fail."""
        response = json.dumps(
            [
                {
                    "id": str(uuid4()),
                    "work": "   ",
                    "struggle": "test",
                    "intention": "test",
                    "created_at": "2025-01-14T10:00:00Z",
                }
            ]
        )
        result = validate_journal_api_response(response)
        assert result.is_valid is False
        assert "work" in result.message

    def test_null_field_value(self):
        """Null field value should fail."""
        response = json.dumps(
            [
                {
                    "id": str(uuid4()),
                    "work": None,
                    "struggle": "test",
                    "intention": "test",
                    "created_at": "2025-01-14T10:00:00Z",
                }
            ]
        )
        result = validate_journal_api_response(response)
        assert result.is_valid is False


class TestRealisticResponses:
    """Tests with realistic responses from journal-starter API."""

    def test_wrapped_response_format(self):
        """Actual journal-starter API response format with entries wrapper."""
        response = json.dumps(
            {
                "entries": [
                    {
                        "id": "a4123fe0-468c-4526-920b-cb112279d7ac",
                        "work": "Studied FastAPI and built my first API endpoints",
                        "struggle": "Understanding async/await syntax",
                        "intention": "Practice PostgreSQL queries",
                        "created_at": "2026-01-11T15:51:39.784641+00:00",
                        "updated_at": "2026-01-11T15:51:39.784641+00:00",
                    }
                ],
                "count": 1,
            }
        )
        result = validate_journal_api_response(response)
        assert result.is_valid is True
        assert "1 entry" in result.message

    def test_wrapped_response_multiple_entries(self):
        """Wrapped format with multiple entries."""
        response = json.dumps(
            {
                "entries": [
                    {
                        "id": str(uuid4()),
                        "work": "Day 1 work",
                        "struggle": "Day 1 struggle",
                        "intention": "Day 1 intention",
                        "created_at": "2026-01-11T10:00:00Z",
                    },
                    {
                        "id": str(uuid4()),
                        "work": "Day 2 work",
                        "struggle": "Day 2 struggle",
                        "intention": "Day 2 intention",
                        "created_at": "2026-01-12T10:00:00Z",
                    },
                ],
                "count": 2,
            }
        )
        result = validate_journal_api_response(response)
        assert result.is_valid is True
        assert "2 entries" in result.message

    def test_realistic_single_entry(self):
        """Realistic response from a working journal-starter API (raw array)."""
        response = json.dumps(
            [
                {
                    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "work": "Studied FastAPI and built my first API endpoints",
                    "struggle": "Understanding async/await syntax and when to use it",
                    "intention": "Practice PostgreSQL queries and database design",
                    "created_at": "2025-01-14T15:30:00.123456",
                    "updated_at": "2025-01-14T15:30:00.123456",
                }
            ]
        )
        result = validate_journal_api_response(response)
        assert result.is_valid is True
        assert "🎉" in result.message

    def test_realistic_multiple_entries(self):
        """Multiple realistic entries showing progress over days."""
        response = json.dumps(
            [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "work": "Set up the development environment with Docker",
                    "struggle": "Getting the database container to connect properly",
                    "intention": "Start implementing the POST endpoint",
                    "created_at": "2025-01-12T09:00:00Z",
                    "updated_at": "2025-01-12T09:00:00Z",
                },
                {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "work": "Implemented POST /entries endpoint",
                    "struggle": "Pydantic validation errors were confusing",
                    "intention": "Add GET single entry endpoint",
                    "created_at": "2025-01-13T10:30:00Z",
                    "updated_at": "2025-01-13T10:30:00Z",
                },
                {
                    "id": "33333333-3333-3333-3333-333333333333",
                    "work": "Completed GET /entries/{id} and DELETE endpoints",
                    "struggle": "Handling 404 errors properly",
                    "intention": "Start working on the AI analysis feature",
                    "created_at": "2025-01-14T14:00:00Z",
                    "updated_at": "2025-01-14T16:00:00Z",
                },
            ]
        )
        result = validate_journal_api_response(response)
        assert result.is_valid is True
        assert "3 entries" in result.message

    def test_swagger_ui_copied_response(self):
        """Response format as typically copied from Swagger UI."""
        # Swagger UI often formats JSON with 2-space indentation
        response = """[
  {
    "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "work": "Learned about REST API design principles",
    "struggle": "Choosing between query params and path params",
    "intention": "Review FastAPI documentation on dependencies",
    "created_at": "2025-01-14T18:45:30.000000",
    "updated_at": "2025-01-14T18:45:30.000000"
  }
]"""
        result = validate_journal_api_response(response)
        assert result.is_valid is True
