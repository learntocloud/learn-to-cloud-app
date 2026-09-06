"""Exercise challenge-only verification through the real HTTP request boundary."""

import asyncio
import json
import re
from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx
import pytest

from learn_to_cloud_shared.verification import deployed_api

_CHALLENGE_ID = "12345678-1234-4567-89ab-123456789abc"
_POST_ID = "87654321-4321-4567-89ab-987654321abc"
_SUCCESS_MESSAGE = (
    "Deployed API verified! Ownership confirmed via challenge-response. "
    "Live AI analysis verified."
)


class JournalApi:
    """A transport-backed Journal API with independently configurable responses."""

    def __init__(self):
        self.requests = []
        self.span = MagicMock()
        self.responses = {}
        self.current_changes = {}
        self.work_transform = None
        self.missing_fields = ()
        self.historical = []
        self.include_current = True
        self.challenge = {}

    def handle(self, request):
        self.requests.append(request)
        assert request.method in {"GET", "POST"}
        if request.url.path.endswith("/analyze"):
            operation = "analyze"
            response = httpx.Response(
                200,
                json={
                    "entry_id": request.url.path.split("/")[-2],
                    "sentiment": "neutral",
                    "summary": "The learner deployed a working API.",
                    "topics": ["deployment"],
                },
            )
        elif request.method == "POST":
            operation = "create"
            self.challenge = {
                "id": _CHALLENGE_ID,
                **json.loads(request.content),
                "created_at": "2026-01-01T00:00:00Z",
            }
            response = httpx.Response(201, json={"entry": self.challenge})
        else:
            assert request.method == "GET"
            operation = "list"
            current = {**self.challenge, **self.current_changes}
            if self.work_transform is not None:
                current["work"] = self.work_transform(current["work"])
            for field in self.missing_fields:
                current.pop(field)
            entries = [*self.historical]
            if self.include_current:
                entries.append(current)
            response = httpx.Response(200, json={"entries": entries, "count": 0})

        response = self.responses.get(operation, response)
        if isinstance(response, BaseException):
            raise response
        return response

    async def run(self, url="https://learner.example"):
        operation = deployed_api._fetch_with_retry.retry_with(sleep=AsyncMock())
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(self.handle),
            timeout=7.0,
            follow_redirects=False,
        ) as client:
            with (
                patch.object(
                    asyncio.get_running_loop(),
                    "getaddrinfo",
                    AsyncMock(return_value=[(2, 1, 6, "", ("8.8.8.8", 443))]),
                ),
                patch.object(
                    deployed_api, "_get_client", AsyncMock(return_value=client)
                ),
                patch.object(
                    deployed_api.trace, "get_current_span", return_value=self.span
                ),
                patch.object(deployed_api, "_fetch_with_retry", operation),
            ):
                return await deployed_api.validate_deployed_api(url)


@pytest.fixture
def journal():
    api = JournalApi()
    yield api
    assert all(request.method != "DELETE" for request in api.requests)


@pytest.mark.parametrize(
    ("url", "base_path"),
    [
        ("https://learner.example", ""),
        (" https://learner.example/entries/ ", ""),
        ("https://learner.example/v1/", "/v1"),
        (" https://learner.example/v1/entries/ ", "/v1"),
    ],
)
async def test_current_challenge_alone_verifies_full_request_contract(
    journal, url, base_path
):
    result = await journal.run(url)

    assert result.verification_completed
    assert result.is_valid
    assert result.message == _SUCCESS_MESSAGE
    assert [(request.method, request.url.path) for request in journal.requests] == [
        ("POST", f"{base_path}/entries"),
        ("GET", f"{base_path}/entries"),
        ("POST", f"{base_path}/entries/{_CHALLENGE_ID}/analyze"),
    ]
    create, listing, analysis = journal.requests
    body = json.loads(create.content)
    assert body == {
        "work": journal.challenge["work"],
        "struggle": "Every challenge is a chance to learn.",
        "intention": "Keep building, learning, and making progress.",
    }
    assert re.fullmatch(
        r"Nice work getting your Journal API online! \(ltc-verify-[0-9a-f]{32}\)",
        body["work"],
    )
    assert all(0 < len(value) <= 256 for value in body.values())
    assert all(request.content == b"" for request in (listing, analysis))
    assert all(
        request.headers["Accept"] == "application/json" for request in journal.requests
    )
    assert analysis.extensions["timeout"] == {
        "connect": 30.0,
        "read": 30.0,
        "write": 30.0,
        "pool": 30.0,
    }
    assert create.extensions["timeout"]["read"] == 7.0
    journal.span.set_attribute.assert_has_calls(
        [
            call("verification.deployed_api.challenge_verified", True),
            call("verification.deployed_api.verified", True),
            call("verification.deployed_api.ai_verified", True),
        ]
    )
    journal.span.add_event.assert_not_called()


async def test_malformed_historical_entries_are_not_validated(journal):
    journal.historical = [
        None,
        [],
        "not an entry",
        123,
        {},
        {"work": "historical entry with missing fields"},
        {
            "id": "not-a-uuid",
            "work": "old work",
            "struggle": [],
            "intention": "x" * 257,
            "created_at": "not-a-date",
            "updated_at": 123,
        },
        {"id": None, "work": "ltc-verify-previous-attempt"},
    ]

    result = await journal.run()

    assert result.verification_completed
    assert result.is_valid
    assert result.message == _SUCCESS_MESSAGE
    assert len(journal.requests) == 3


@pytest.mark.parametrize("previous_challenge", [False, True])
async def test_historical_entries_cannot_replace_current_nonce(
    journal, previous_challenge
):
    journal.include_current = False
    if previous_challenge:
        journal.historical = [
            {
                "id": _POST_ID,
                "work": (
                    "Nice work getting your Journal API online! "
                    "(ltc-verify-00000000000000000000000000000000)"
                ),
                "struggle": "Every challenge is a chance to learn.",
                "intention": "Keep building, learning, and making progress.",
                "created_at": "2026-01-01T00:00:00Z",
            }
        ]

    result = await journal.run()

    assert result.verification_completed
    assert not result.is_valid
    assert "Ownership verification failed" in result.message
    assert [request.method for request in journal.requests] == ["POST", "GET"]
    journal.span.add_event.assert_called_once_with("deployed_api.challenge_failed")


async def test_retained_friendly_entry_cannot_verify_a_later_attempt(journal):
    first_result = await journal.run()
    assert first_result.is_valid
    retained_entry = dict(journal.challenge)
    journal.historical = [retained_entry]
    journal.include_current = False
    journal.requests.clear()

    result = await journal.run()

    assert journal.challenge["work"] != retained_entry["work"]
    assert result.verification_completed
    assert not result.is_valid
    assert "Ownership verification failed" in result.message
    assert [request.method for request in journal.requests] == ["POST", "GET"]
    assert journal.historical == [retained_entry]


@pytest.mark.parametrize(
    "transform",
    [
        pytest.param(lambda work: work.split("(")[1][:-1], id="nonce-only"),
        pytest.param(lambda work: f"Extra text {work}", id="prepended-text"),
        pytest.param(lambda work: f"{work} Extra text", id="appended-text"),
    ],
)
async def test_challenge_matching_requires_exact_friendly_work(journal, transform):
    journal.work_transform = transform

    result = await journal.run()

    assert result.verification_completed
    assert not result.is_valid
    assert "Ownership verification failed" in result.message
    assert [request.method for request in journal.requests] == ["POST", "GET"]
    journal.span.add_event.assert_called_once_with("deployed_api.challenge_failed")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", "not-a-uuid", "invalid id"),
        ("id", "12345678-1234-1567-89ab-123456789abc", "invalid id"),
        ("id", "", "invalid id"),
        ("struggle", None, "must be a string"),
        ("struggle", [], "must be a string"),
        ("struggle", " ", "cannot be empty"),
        ("intention", "x" * 257, "exceeds max length"),
        ("created_at", "not-a-date", "invalid created_at"),
        ("created_at", 123, "invalid created_at"),
        ("updated_at", "not-a-date", "invalid updated_at"),
        ("updated_at", [], "invalid updated_at"),
    ],
)
async def test_invalid_current_fields_fail_without_analysis_or_deletion(
    journal, field, value, message
):
    journal.current_changes[field] = value

    result = await journal.run()

    assert result.verification_completed
    assert not result.is_valid
    assert result.message.startswith("Challenge entry")
    assert message in result.message
    assert [request.method for request in journal.requests] == ["POST", "GET"]


@pytest.mark.parametrize("field", ["id", "struggle", "intention", "created_at"])
@pytest.mark.parametrize("post_has_id", [False, True])
async def test_missing_current_fields_fail_regardless_of_post_id(
    journal, field, post_has_id
):
    journal.missing_fields = (field,)
    if not post_has_id:
        journal.responses["create"] = httpx.Response(201, json={})

    result = await journal.run()

    assert result.verification_completed
    assert not result.is_valid
    assert result.message == f"Challenge entry missing fields: {field}"
    assert [request.method for request in journal.requests] == ["POST", "GET"]


@pytest.mark.parametrize("invalid_id", [None, 123, [], {}, ["not-an-id"]])
@pytest.mark.parametrize("post_has_id", [False, True])
async def test_nonstring_get_ids_fail_without_analysis_or_deletion(
    journal, invalid_id, post_has_id
):
    journal.current_changes["id"] = invalid_id
    if not post_has_id:
        journal.responses["create"] = httpx.Response(201, json={})

    result = await journal.run()

    assert result.verification_completed
    assert not result.is_valid
    assert result.message == "Challenge entry has invalid id (expected UUID format)"
    assert [request.method for request in journal.requests] == ["POST", "GET"]


async def test_invalid_string_get_id_without_post_id_is_completed_failure(journal):
    journal.responses["create"] = httpx.Response(201, json={})
    journal.current_changes["id"] = "invalid-uuid"

    result = await journal.run()

    assert result.verification_completed
    assert not result.is_valid
    assert "invalid id" in result.message
    assert [request.method for request in journal.requests] == ["POST", "GET"]


@pytest.mark.parametrize(
    "post_body",
    [
        {},
        {"entry": {}},
        {"entry": None},
        {"entry": {"id": None}},
        {"entry": {"id": 123}},
        {"entry": {"id": []}},
        {"entry": {"id": {"private": "value"}}},
    ],
)
async def test_missing_or_nonstring_post_id_falls_back_to_get(journal, post_body):
    journal.responses["create"] = httpx.Response(201, json=post_body)

    result = await journal.run()

    assert result.verification_completed
    assert result.is_valid
    assert journal.requests[2].url.path == f"/entries/{_CHALLENGE_ID}/analyze"
    assert len(journal.requests) == 3


@pytest.mark.parametrize("wrapped", [False, True])
async def test_post_id_takes_precedence_over_discovered_get_id(journal, wrapped):
    post_body = {"id": _POST_ID}
    journal.responses["create"] = httpx.Response(
        200, json={"entry": post_body} if wrapped else post_body
    )

    result = await journal.run()

    assert result.verification_completed
    assert result.is_valid
    assert journal.requests[2].url.path == f"/entries/{_POST_ID}/analyze"
    assert len(journal.requests) == 3


@pytest.mark.parametrize("content", [b"not-json", b"\xff"])
@pytest.mark.parametrize("operation", ["create", "list", "analyze"])
async def test_malformed_response_json_completes_without_deleting_entry(
    journal, operation, content
):
    journal.responses[operation] = httpx.Response(200, content=content)

    result = await journal.run()

    assert result.verification_completed
    assert result.is_valid is (operation == "create")
    if operation != "create":
        assert "did not return valid JSON" in result.message
    expected_methods = ["POST", "GET"]
    if operation != "list":
        expected_methods.append("POST")
    assert [request.method for request in journal.requests] == expected_methods


@pytest.mark.parametrize(
    "envelope", [[], {}, {"entries": {}}, {"entries": None}, {"entries": "bad"}]
)
async def test_malformed_get_envelope_fails_before_analysis(journal, envelope):
    journal.responses["list"] = httpx.Response(200, json=envelope)

    result = await journal.run()

    assert result.verification_completed
    assert not result.is_valid
    assert 'must return {"entries": [...], "count": N}' in result.message
    assert [request.method for request in journal.requests] == ["POST", "GET"]


@pytest.mark.parametrize("sentiment", [None, 123, [], {}])
async def test_nonstring_analysis_sentiment_is_completed_failure(journal, sentiment):
    journal.responses["analyze"] = httpx.Response(
        200,
        json={
            "entry_id": _CHALLENGE_ID,
            "sentiment": sentiment,
            "summary": "A summary",
            "topics": ["cloud"],
        },
    )

    result = await journal.run()

    assert result.verification_completed
    assert not result.is_valid
    assert "sentiment" in result.message
    assert [request.method for request in journal.requests] == [
        "POST",
        "GET",
        "POST",
    ]


@pytest.mark.parametrize(
    ("failure", "category", "status"),
    [
        (501, "server_error", 501),
        (503, "server_error", 503),
        (httpx.ReadTimeout, "timeout", None),
        (httpx.ConnectError, "request_error", None),
    ],
)
async def test_analysis_failure_preserves_entry_and_safe_diagnostics_without_retry(
    journal, failure, category, status
):
    journal.responses["analyze"] = (
        httpx.Response(failure, text="private learner details")
        if isinstance(failure, int)
        else failure("private learner details")
    )

    result = await journal.run()

    assert result.verification_completed
    assert not result.is_valid
    if status == 501:
        assert result.message == (
            "POST /entries/{id}/analyze is not implemented. Complete the "
            "Journal API AI analysis task and deploy it."
        )
    assert [request.method for request in journal.requests] == [
        "POST",
        "GET",
        "POST",
    ]
    assert journal.requests[2].extensions["timeout"]["read"] == 30.0
    attributes = {
        "error.type": category,
        "verification.operation": "POST /entries/{id}/analyze",
    }
    if status is not None:
        attributes["http.response.status_code"] = status
        journal.span.set_attribute.assert_any_call("http.response.status_code", status)
    journal.span.add_event.assert_called_once_with(
        f"deployed_api.{category}", attributes
    )
    assert "private learner" not in result.message
    assert "private learner" not in str(journal.span.mock_calls)
    assert "learner.example" not in str(journal.span.mock_calls)
    assert journal.challenge["work"] not in str(journal.span.mock_calls)


@pytest.mark.parametrize("operation", ["create", "list", "analyze"])
async def test_private_response_peer_fails_without_deleting_entry(journal, operation):
    stream = MagicMock()
    stream.get_extra_info.return_value = ("10.0.0.1", 443)
    journal.responses[operation] = httpx.Response(
        200, extensions={"network_stream": stream}
    )

    result = await journal.run()

    assert result.verification_completed
    assert not result.is_valid
    assert result.message == "URL must point to a publicly accessible server."
    expected_methods = {
        "create": ["POST"],
        "list": ["POST", "GET"],
        "analyze": ["POST", "GET", "POST"],
    }
    assert [request.method for request in journal.requests] == (
        expected_methods[operation]
    )
    journal.span.add_event.assert_called_once_with(
        "deployed_api.ssrf_blocked", {"verification.reason": "dns_rebinding"}
    )
    assert "10.0.0.1" not in str(journal.span.mock_calls)


@pytest.mark.parametrize("operation", ["create", "list", "analyze"])
@pytest.mark.parametrize("error_type", [ValueError, TypeError, asyncio.CancelledError])
async def test_unexpected_errors_and_cancellation_propagate_without_deletion(
    journal, operation, error_type
):
    error = error_type("unexpected failure")
    journal.responses[operation] = error

    with pytest.raises(error_type) as raised:
        await journal.run()

    assert raised.value is error
    expected_methods = {
        "create": ["POST"],
        "list": ["POST", "GET"],
        "analyze": ["POST", "GET", "POST"],
    }
    assert [request.method for request in journal.requests] == (
        expected_methods[operation]
    )
    journal.span.add_event.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "http://learner.example",
        "https://learner.example:invalid",
        "https://learner.example:70000",
        "https://learner.example:0",
        "https://[invalid",
    ],
)
async def test_invalid_url_is_a_completed_failure_without_requests(journal, url):
    result = await journal.run(url)

    assert result.verification_completed
    assert not result.is_valid
    assert "valid HTTP(S) URL" in result.message
    assert journal.requests == []
