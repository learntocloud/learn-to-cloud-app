"""CREATE -> ANALYZE -> REPORT uses two POSTs and leaves the entry untouched."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx
import pytest

from learn_to_cloud_shared.verification import deployed_api

_ENTRY_ID = "entry-123"
_SUCCESS_MESSAGE = (
    "Deployed API verified! Entry creation and live AI analysis confirmed."
)
_ENTRY_BODY = {
    "work": "Submitted deployed API for verification.",
    "struggle": "Verifying that entry creation and AI analysis work after deployment.",
    "intention": "Review the verification result and address any reported issues.",
}


def _analysis(entry_id=_ENTRY_ID):
    return {
        "entry_id": entry_id,
        "sentiment": "neutral",
        "summary": "The learner deployed a working API.",
        "topics": ["deployment"],
    }


class JournalApi:
    """A transport fixture with independently configurable create/analyze responses."""

    def __init__(self):
        self.requests = []
        self.span = MagicMock()
        self.responses = {
            "create": httpx.Response(201, json={"entry": {"id": _ENTRY_ID}}),
            "analyze": httpx.Response(200, json=_analysis()),
        }

    def handle(self, request):
        self.requests.append(request)
        assert request.method == "POST"
        assert len(self.requests) <= 2
        operation = "analyze" if request.url.path.endswith("/analyze") else "create"
        response = self.responses[operation]
        if isinstance(response, BaseException):
            raise response
        return response

    async def run(self, url="https://learner.example"):
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
            ):
                return await deployed_api.validate_deployed_api(url)


@pytest.fixture
def journal():
    api = JournalApi()
    yield api
    assert all(request.method == "POST" for request in api.requests)
    assert len(api.requests) <= 2


@pytest.mark.parametrize(
    ("url", "base_path"),
    [
        ("https://learner.example", ""),
        (" https://learner.example/entries/ ", ""),
        ("https://learner.example/v1/", "/v1"),
        (" https://learner.example/v1/entries/ ", "/v1"),
    ],
)
async def test_success_creates_then_analyzes_with_no_other_requests(
    journal, url, base_path
):
    result = await journal.run(url)

    assert result.verification_completed
    assert result.is_valid
    assert result.message == _SUCCESS_MESSAGE
    assert [(request.method, request.url.path) for request in journal.requests] == [
        ("POST", f"{base_path}/entries"),
        ("POST", f"{base_path}/entries/{_ENTRY_ID}/analyze"),
    ]
    create, analysis = journal.requests
    assert json.loads(create.content) == _ENTRY_BODY
    assert all(0 < len(value) <= 256 for value in _ENTRY_BODY.values())
    assert analysis.content == b""
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
    assert journal.span.set_attribute.call_args_list == [
        call("verification.deployed_api.verified", True),
        call("verification.deployed_api.ai_verified", True),
    ]
    journal.span.add_event.assert_not_called()


@pytest.mark.parametrize("status", [200, 201])
@pytest.mark.parametrize("wrapped", [False, True])
async def test_create_requires_only_a_string_id_not_entry_fields(
    journal, status, wrapped
):
    entry = {"id": _ENTRY_ID, "work": [], "created_at": "not-a-date"}
    journal.responses["create"] = httpx.Response(
        status, json={"entry": entry} if wrapped else entry
    )

    result = await journal.run()

    assert result.verification_completed
    assert result.is_valid
    assert len(journal.requests) == 2


@pytest.mark.parametrize(
    ("entry_id", "encoded"),
    [
        ("not-a-uuid", b"not-a-uuid"),
        ("part/child", b"part%2Fchild"),
        ("part?query#fragment", b"part%3Fquery%23fragment"),
        ("100% ready", b"100%25%20ready"),
        (" entry ", b"%20entry%20"),
        ("caf\u00e9", b"caf%C3%A9"),
    ],
)
async def test_created_id_is_encoded_as_one_path_segment(journal, entry_id, encoded):
    journal.responses["create"] = httpx.Response(201, json={"id": entry_id})
    journal.responses["analyze"] = httpx.Response(200, json=_analysis(entry_id))

    result = await journal.run()

    assert result.verification_completed
    assert result.is_valid
    assert len(journal.requests) == 2
    assert journal.requests[1].url.raw_path == b"/entries/" + encoded + b"/analyze"
    assert journal.requests[1].url.query == b""
    assert journal.requests[1].url.fragment == ""


async def test_invalid_unicode_id_fails_before_analysis(journal):
    journal.responses["create"] = httpx.Response(
        201, content=b'{"entry":{"id":"\\ud800"}}'
    )

    result = await journal.run()

    assert result.verification_completed
    assert not result.is_valid
    assert result.message == "POST /entries returned an invalid entry ID."
    assert len(journal.requests) == 1


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {},
        {"entry": {}},
        {"entry": None},
        {"entry": {"id": None}},
        {"entry": {"id": 123}},
        {"entry": {"id": []}},
        {"entry": {"id": {}}},
        {"id": ""},
        {"id": " \t\n "},
    ],
)
async def test_missing_nonstring_or_blank_id_stops_after_create(journal, body):
    journal.responses["create"] = httpx.Response(201, content=json.dumps(body).encode())

    result = await journal.run()

    assert result.verification_completed
    assert not result.is_valid
    assert result.message == (
        "POST /entries must return the created entry with a non-empty string id."
    )
    assert len(journal.requests) == 1


@pytest.mark.parametrize("content", [b"not-json", b"\xff"])
@pytest.mark.parametrize("operation", ["create", "analyze"])
async def test_malformed_response_json_is_a_completed_failure(
    journal, operation, content
):
    journal.responses[operation] = httpx.Response(200, content=content)

    result = await journal.run()

    assert result.verification_completed
    assert not result.is_valid
    step = "POST /entries" if operation == "create" else "POST /entries/{id}/analyze"
    assert result.message == f"{step} did not return valid JSON."
    assert len(journal.requests) == (1 if operation == "create" else 2)


@pytest.mark.parametrize("status", [202, 204, 301, 400, 401, 403, 404, 422, 429])
@pytest.mark.parametrize("operation", ["create", "analyze"])
async def test_unexpected_status_stops_without_retries_or_redirects(
    journal, operation, status
):
    journal.responses[operation] = httpx.Response(
        status, headers={"Location": "https://redirect.example"}
    )

    result = await journal.run()

    assert result.verification_completed
    assert not result.is_valid
    assert str(status) in result.message
    if operation == "create" and status == 422:
        assert result.message == (
            "POST /entries returned 422 (validation error). "
            "Ensure POST /entries accepts {work, struggle, intention}."
        )
    assert len(journal.requests) == (1 if operation == "create" else 2)
    assert all(request.url.host == "learner.example" for request in journal.requests)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("entry_id", "other-entry", "entry_id"),
        ("sentiment", "mixed", "sentiment"),
        ("sentiment", None, "sentiment"),
        ("sentiment", 123, "sentiment"),
        ("sentiment", [], "sentiment"),
        ("sentiment", {}, "sentiment"),
        ("summary", "", "summary"),
        ("summary", " ", "summary"),
        ("summary", None, "summary"),
        ("topics", [], "topics"),
        ("topics", "cloud", "topics"),
        ("topics", ["cloud", ""], "topics"),
        ("topics", ["cloud", 123], "topics"),
    ],
)
async def test_invalid_analysis_fields_are_completed_failures(
    journal, field, value, message
):
    analysis = _analysis()
    analysis[field] = value
    journal.responses["analyze"] = httpx.Response(200, json=analysis)

    result = await journal.run()

    assert result.verification_completed
    assert not result.is_valid
    assert message in result.message
    assert len(journal.requests) == 2
    journal.span.set_attribute.assert_not_called()


@pytest.mark.parametrize("body", [[], "not an object", None])
async def test_analysis_requires_a_json_object(journal, body):
    journal.responses["analyze"] = httpx.Response(
        200, content=json.dumps(body).encode()
    )

    result = await journal.run()

    assert result.verification_completed
    assert not result.is_valid
    assert result.message == "AI analysis must return a JSON object."
    assert len(journal.requests) == 2


@pytest.mark.parametrize("operation", ["create", "analyze"])
@pytest.mark.parametrize(
    ("failure", "category"),
    [
        (500, "server_error"),
        (501, "server_error"),
        (503, "server_error"),
        (httpx.ReadTimeout, "timeout"),
        (httpx.ConnectError, "request_error"),
    ],
)
async def test_failures_are_not_retried_and_emit_safe_step_diagnostics(
    journal, operation, failure, category
):
    journal.responses[operation] = (
        httpx.Response(failure, text="private learner details")
        if isinstance(failure, int)
        else failure("private learner details")
    )

    result = await journal.run()

    assert result.verification_completed
    assert not result.is_valid
    assert len(journal.requests) == (1 if operation == "create" else 2)
    step = "POST /entries" if operation == "create" else "POST /entries/{id}/analyze"
    if operation == "analyze" and failure == 501:
        assert result.message == (
            "POST /entries/{id}/analyze is not implemented. Complete the "
            "Journal API AI analysis task and deploy it."
        )
    else:
        assert result.message.startswith(f"{step}:")
    attributes = {"error.type": category, "verification.operation": step}
    if isinstance(failure, int):
        attributes["http.response.status_code"] = failure
        journal.span.set_attribute.assert_any_call("http.response.status_code", failure)
    journal.span.set_attribute.assert_any_call("error.type", category)
    journal.span.add_event.assert_called_once_with(
        f"deployed_api.{category}", attributes
    )
    for private_value in ("private learner", "learner.example", _ENTRY_BODY["work"]):
        assert private_value not in result.message
        assert private_value not in str(journal.span.mock_calls)
    journal.span.record_exception.assert_not_called()


@pytest.mark.parametrize("operation", ["create", "analyze"])
async def test_private_response_peer_stops_without_more_requests(journal, operation):
    stream = MagicMock()
    stream.get_extra_info.return_value = ("10.0.0.1", 443)
    journal.responses[operation] = httpx.Response(
        200, extensions={"network_stream": stream}
    )

    result = await journal.run()

    assert result.verification_completed
    assert not result.is_valid
    assert result.message == "URL must point to a publicly accessible server."
    assert len(journal.requests) == (1 if operation == "create" else 2)
    journal.span.add_event.assert_called_once_with(
        "deployed_api.ssrf_blocked", {"verification.reason": "dns_rebinding"}
    )
    assert "10.0.0.1" not in str(journal.span.mock_calls)


@pytest.mark.parametrize("operation", ["create", "analyze"])
@pytest.mark.parametrize("error_type", [ValueError, TypeError, asyncio.CancelledError])
async def test_programming_errors_and_cancellation_propagate_without_more_requests(
    journal, operation, error_type
):
    error = error_type("unexpected failure")
    journal.responses[operation] = error

    with pytest.raises(error_type) as raised:
        await journal.run()

    assert raised.value is error
    assert len(journal.requests) == (1 if operation == "create" else 2)
    journal.span.add_event.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not-a-url",
        "http://learner.example",
        "https://learner.example:invalid",
        "https://learner.example:70000",
        "https://learner.example:0",
        "https://[invalid",
    ],
)
async def test_invalid_url_is_completed_without_requests(journal, url):
    result = await journal.run(url)

    assert result.verification_completed
    assert not result.is_valid
    assert result.message == (
        "Please submit a valid HTTP(S) URL."
        if url
        else "Please submit your deployed API base URL."
    )
    assert journal.requests == []
