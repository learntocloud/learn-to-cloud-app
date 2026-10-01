"""One boundary for timing, classifying, tracing, and measuring outbound calls.

Every dependency call records ``learn_to_cloud.dependency.duration`` (never
sampled, the basis for alerts) with a bounded ``error.type``. Calls that no
library instruments also get a CLIENT span here; calls already traced by an
instrumentor (openai's httpx client, azure-core, SQLAlchemy) only get the
metric so spans are never duplicated.
"""

from __future__ import annotations

import asyncio
import contextvars
import socket
import ssl
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager, nullcontext
from enum import StrEnum
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

import httpx
from opentelemetry import metrics, trace
from opentelemetry.instrumentation.utils import suppress_http_instrumentation
from opentelemetry.trace import SpanKind, Status, StatusCode
from tenacity import RetryCallState


class Dependency(StrEnum):
    GITHUB = "github"
    GITHUB_OAUTH = "github_oauth"
    DEPLOYED_API = "deployed_api"
    FOUNDRY = "foundry"
    ENTRA = "entra"
    POSTGRES = "postgres"


DEPENDENCY_NAME = "learn_to_cloud.dependency.name"
DEPENDENCY_OPERATION = "learn_to_cloud.dependency.operation"
DEPENDENCY_ATTEMPT = "learn_to_cloud.dependency.attempt"
ERROR_TYPE = "error.type"
OTHER = "_OTHER"

ERROR_TYPES = frozenset(
    {
        "timeout.connect",
        "timeout.read",
        "timeout.write",
        "timeout.pool",
        "timeout",
        "dns",
        "tls",
        "connection",
        "auth",
        "rate_limit",
        "http_4xx",
        "http_5xx",
        "cancelled",
        OTHER,
    }
)

_HTTP_METHODS = frozenset(
    {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "CONNECT", "TRACE"}
)
_HTTPX_MODULES = frozenset({"httpx", "httpx2"})
_HTTPX_ERROR_TYPES = {
    "ConnectTimeout": "timeout.connect",
    "ReadTimeout": "timeout.read",
    "WriteTimeout": "timeout.write",
    "PoolTimeout": "timeout.pool",
    "TimeoutException": "timeout",
    "NetworkError": "connection",
    "ProtocolError": "connection",
    "ProxyError": "connection",
}
_AZURE_AUTH_ERRORS = frozenset(
    {"ClientAuthenticationError", "CredentialUnavailableError"}
)
_AZURE_TRANSPORT_ERRORS = frozenset({"ServiceRequestError", "ServiceResponseError"})
_ASYNCPG_AUTH_ERRORS = frozenset(
    {"InvalidPasswordError", "InvalidAuthorizationSpecificationError"}
)

_meter = metrics.get_meter("learn_to_cloud")
_DURATION = _meter.create_histogram(
    name="learn_to_cloud.dependency.duration",
    unit="s",
    description="Duration of each outbound dependency attempt",
    explicit_bucket_boundaries_advisory=[
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        30.0,
        60.0,
    ],
)
_tracer = trace.get_tracer("learn_to_cloud.outbound")

_resend_count: contextvars.ContextVar[int] = contextvars.ContextVar(
    "learn_to_cloud_outbound_resend_count", default=0
)


def track_retry_attempt(retry_state: RetryCallState) -> None:
    """Tenacity ``before`` hook that marks the next outbound attempt as a resend."""
    _resend_count.set(retry_state.attempt_number - 1)


def sanitize_url(url: object) -> str:
    """Drop credentials, query string, and fragment from a URL."""
    parts = urlsplit(str(url))
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    netloc = f"{host}:{parts.port}" if parts.port else host
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def classify_status(
    status_code: int, headers: Mapping[str, str] | None = None
) -> str | None:
    """Return the error type for an HTTP status, or ``None`` when it succeeded."""
    if status_code < 400:
        return None
    if status_code == 429:
        return "rate_limit"
    if status_code == 403 and headers is not None:
        if headers.get("x-ratelimit-remaining") == "0" or "retry-after" in headers:
            return "rate_limit"
    if status_code in (401, 407):
        return "auth"
    if status_code >= 500:
        return "http_5xx"
    return "http_4xx"


def _chain(exc: BaseException) -> list[BaseException]:
    seen: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and all(current is not item for item in seen):
        seen.append(current)
        current = current.__cause__ or current.__context__
    return seen


def _classify_one(exc: BaseException) -> str | None:
    if isinstance(exc, asyncio.CancelledError):
        return "cancelled"
    if isinstance(exc, socket.gaierror):
        return "dns"
    if isinstance(exc, ssl.SSLError):
        return "tls"
    for cls in type(exc).__mro__:
        module = cls.__module__.split(".")[0]
        name = cls.__name__
        if module in _HTTPX_MODULES and name in _HTTPX_ERROR_TYPES:
            return _HTTPX_ERROR_TYPES[name]
        if module == "openai":
            if name == "APITimeoutError":
                return "timeout"
            if name == "APIStatusError":
                status = getattr(exc, "status_code", None)
                if isinstance(status, int):
                    return classify_status(status) or OTHER
            if name == "APIConnectionError":
                return "connection"
        if module == "azure" and name in _AZURE_AUTH_ERRORS:
            return "auth"
        if module == "azure" and name in _AZURE_TRANSPORT_ERRORS:
            return "connection"
        if module == "asyncpg" and name in _ASYNCPG_AUTH_ERRORS:
            return "auth"
        if module == "asyncpg" and name == "PostgresConnectionError":
            return "connection"
        if module == "asyncpg" and name == "QueryCanceledError":
            return "timeout"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, ConnectionError):
        return "connection"
    return None


def classify(exc: BaseException) -> str:
    """Map any dependency failure to one bounded ``error.type`` value.

    The most specific cause wins, so ``openai.APITimeoutError`` raised from
    ``httpx.ConnectTimeout`` becomes ``timeout.connect`` and an
    ``httpx.ConnectError`` caused by a DNS failure becomes ``dns``.
    """
    found = [result for item in _chain(exc) if (result := _classify_one(item))]
    if not found:
        return OTHER
    for specific in found:
        if specific not in {"timeout", "connection"}:
            return specific
    return found[-1]


def _bounded(value: str, allowed: frozenset[str]) -> str:
    return value if value in allowed else OTHER


def _attempt_bucket(resend_count: int) -> str:
    return "first" if resend_count <= 0 else "retry"


class OutboundCall:
    """Mutable outcome of one outbound attempt."""

    def __init__(self, span: trace.Span | None) -> None:
        self.span = span
        self.status_code: int | None = None
        self.error_type: str | None = None

    def set_response(
        self, status_code: int, headers: Mapping[str, str] | None = None
    ) -> None:
        """Record the response status and classify unsuccessful statuses."""
        self.status_code = status_code
        self.error_type = classify_status(status_code, headers)


@asynccontextmanager
async def outbound_call(
    dependency: Dependency,
    operation: str,
    *,
    span_name: str | None = None,
    span_attributes: Mapping[str, Any] | None = None,
) -> AsyncIterator[OutboundCall]:
    """Time and classify one attempt; open a CLIENT span when ``span_name`` is set."""
    resend_count = _resend_count.get()
    _resend_count.set(0)
    span_context = (
        nullcontext(None)
        if span_name is None
        else _tracer.start_as_current_span(
            span_name,
            kind=SpanKind.CLIENT,
            attributes={DEPENDENCY_NAME: dependency.value, **(span_attributes or {})},
            record_exception=False,
            set_status_on_exception=False,
        )
    )
    with span_context as span:
        if span is not None and resend_count:
            span.set_attribute("http.request.resend_count", resend_count)
        call = OutboundCall(span)
        started = time.perf_counter()
        try:
            yield call
        except BaseException as exc:
            call.error_type = classify(exc)
            raise
        finally:
            _finish(call, dependency, operation, resend_count, started)


def record_attempt(
    dependency: Dependency,
    operation: str,
    duration_seconds: float,
    *,
    error_type: str | None = None,
    status_code: int | None = None,
    resend_count: int = 0,
) -> None:
    """Record one attempt measured outside :func:`outbound_call`."""
    attributes: dict[str, str | int] = {
        DEPENDENCY_NAME: dependency.value,
        DEPENDENCY_OPERATION: operation,
        DEPENDENCY_ATTEMPT: _attempt_bucket(resend_count),
    }
    if status_code is not None:
        attributes["http.response.status_code"] = status_code
    if error_type is not None:
        attributes[ERROR_TYPE] = error_type
    _DURATION.record(duration_seconds, attributes)


def _finish(
    call: OutboundCall,
    dependency: Dependency,
    operation: str,
    resend_count: int,
    started: float,
) -> None:
    record_attempt(
        dependency,
        operation,
        time.perf_counter() - started,
        error_type=call.error_type,
        status_code=call.status_code,
        resend_count=resend_count,
    )
    span = call.span
    if span is None or not span.is_recording():
        return
    if call.status_code is not None:
        span.set_attribute("http.response.status_code", call.status_code)
    if call.error_type is not None:
        span.set_attribute(ERROR_TYPE, call.error_type)
        span.set_status(Status(StatusCode.ERROR))


class _AsyncTransport(Protocol):
    async def handle_async_request(self, request: Any) -> Any: ...

    async def aclose(self) -> None: ...


def http_operation(method: str) -> str:
    return _bounded(method.upper(), _HTTP_METHODS)


async def send_measured(
    inner: _AsyncTransport, dependency: Dependency, request: Any
) -> Any:
    """Send an httpx-family request through the shared CLIENT span and metric.

    The inner call runs with HTTP auto-instrumentation suppressed so the
    global httpx instrumentor does not add a second span for the same request.
    Duration covers the attempt up to response headers.
    """
    method = http_operation(request.method)
    url = request.url
    attributes: dict[str, str | int] = {
        "http.request.method": method,
        "url.full": sanitize_url(url),
        "server.address": url.host,
    }
    if url.port is not None:
        attributes["server.port"] = url.port
    async with outbound_call(
        dependency, method, span_name=method, span_attributes=attributes
    ) as call:
        with suppress_http_instrumentation():
            response = await inner.handle_async_request(request)
        call.set_response(response.status_code, response.headers)
        return response


class MeasuredTransport(httpx.AsyncBaseTransport):
    """An ``httpx`` transport that measures every attempt for one dependency."""

    def __init__(
        self, dependency: Dependency, inner: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._dependency = dependency
        self._inner = inner or httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await send_measured(self._inner, self._dependency, request)

    async def aclose(self) -> None:
        await self._inner.aclose()
