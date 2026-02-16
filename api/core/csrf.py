"""CSRF protection middleware — Synchronizer Token Pattern.

Stores a random token in the server-side session and validates it on
unsafe requests (POST, PUT, PATCH, DELETE).  The token can be submitted
via either:

- **Header**: ``X-CSRFToken`` (used automatically by HTMX via a global
  ``htmx:configRequest`` listener in ``base.html``)
- **Form field**: ``csrf_token`` (used by the logout ``<form>`` in the
  navbar)

This is stronger than the Double Submit Cookie pattern because the
token lives in the signed session — an attacker who can set cookies
on a subdomain still cannot forge requests.
"""

from __future__ import annotations

import logging
import secrets
from re import Pattern

from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
_SESSION_KEY = "_csrf_token"
_HEADER_NAME = "x-csrftoken"
_FORM_FIELD = "csrf_token"


class CSRFMiddleware:
    """Synchronizer Token CSRF middleware.

    Args:
        app: The ASGI application.
        exempt_urls: Optional regex patterns for paths that skip CSRF
            checks (e.g. OAuth callbacks that receive external redirects).
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        exempt_urls: list[Pattern[str]] | None = None,
    ) -> None:
        self.app = app
        self.exempt_urls = exempt_urls or []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        # Ensure a CSRF token exists in the session.
        session = scope.get("session")
        if session is None:
            # SessionMiddleware not active — skip CSRF enforcement.
            await self.app(scope, receive, send)
            return

        if _SESSION_KEY not in session:
            session[_SESSION_KEY] = secrets.token_urlsafe(32)

        # Expose the token on scope so templates can read it.
        scope["csrf_token"] = session[_SESSION_KEY]

        if request.method in _SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        if self._url_is_exempt(request.url.path):
            await self.app(scope, receive, send)
            return

        # Validate: check header first, then form body.
        submitted: str | None = request.headers.get(_HEADER_NAME)
        if not submitted:
            content_type = request.headers.get("content-type", "")
            if "application/x-www-form-urlencoded" in content_type:
                form = await request.form()
                value = form.get(_FORM_FIELD)
                if isinstance(value, str):
                    submitted = value
                # Close the form to release resources.
                await form.close()

        if not submitted or not secrets.compare_digest(
            submitted, session[_SESSION_KEY]
        ):
            logger.warning(
                "csrf.validation_failed",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                },
            )
            response = self._error_response(request)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _url_is_exempt(self, path: str) -> bool:
        return any(pattern.match(path) for pattern in self.exempt_urls)

    def _error_response(self, request: Request) -> Response:
        """Return 403 — HTMX-aware so the client can handle it."""
        if "hx-request" in request.headers:
            return PlainTextResponse(
                "CSRF token missing or invalid. Please refresh the page.",
                status_code=403,
            )
        return PlainTextResponse("CSRF token verification failed", status_code=403)
