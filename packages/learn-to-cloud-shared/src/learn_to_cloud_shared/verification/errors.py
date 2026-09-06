"""Provider-independent response data and explicit retry primitives."""

from __future__ import annotations

import httpx

BASE_RETRIABLE: tuple[type[Exception], ...] = (
    httpx.RequestError,
    httpx.TimeoutException,
)


def make_retriable(*extra: type[Exception]) -> tuple[type[Exception], ...]:
    """Append integration-specific errors to the network retry types."""
    return BASE_RETRIABLE + extra


class UpstreamResponseError(Exception):
    """An upstream HTTP response's safe message and structured status."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after
