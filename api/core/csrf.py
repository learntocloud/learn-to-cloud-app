"""CSRF protection middleware — Synchronizer Token Pattern.

Stores a random token in the signed session cookie and validates it on
unsafe requests (POST, PUT, PATCH, DELETE).  The token can be submitted
via either:

- **Header**: ``X-CSRFToken`` (used automatically by HTMX via a global
  ``htmx:configRequest`` listener in ``base.html``)
- **Form field**: ``csrf_token`` (used by the logout ``<form>`` in the
  navbar — only parsed for ``application/x-www-form-urlencoded``; for
  ``multipart/form-data`` uploads, use the header instead)

Defence-in-depth layers:

1. **Synchronizer token** — the primary check.
2. **Origin / Referer verification** — when ``trusted_origins`` are
   configured, the middleware rejects unsafe requests whose ``Origin``
   (or ``Referer``) does not match a trusted origin.  Requests with
   neither header are allowed through to avoid breaking clients behind
   privacy proxies, but a warning is logged.
3. **Fail-closed** — if ``SessionMiddleware`` is not active, unsafe
   requests are rejected instead of silently skipping CSRF enforcement.
"""

from __future__ import annotations

import logging
import secrets
from re import Pattern
from urllib.parse import urlparse

from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
_SESSION_KEY = "_csrf_token"
_HEADER_NAME = "x-csrftoken"
_FORM_FIELD = "csrf_token"


def _normalize_origin(origin: str) -> str:
    """Normalize an origin to ``scheme://host[:port]`` (lower-cased)."""
    parsed = urlparse(origin if "://" in origin else f"https://{origin}")
    scheme = (parsed.scheme or "https").lower()
    host = (parsed.hostname or "").lower()
    port = parsed.port
    # Omit default ports for cleaner comparison.
    if port and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        return f"{scheme}://{host}:{port}"
    return f"{scheme}://{host}"


class CSRFMiddleware:
    """Synchronizer Token CSRF middleware.

    Args:
        app: The ASGI application.
        exempt_urls: Optional regex patterns for paths that skip CSRF
            checks (e.g. OAuth callbacks that receive external redirects).
        trusted_origins: Origins (``scheme://host[:port]``) that are
            allowed to make unsafe requests.  When set, the ``Origin``
            or ``Referer`` header is verified before token validation.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        exempt_urls: list[Pattern[str]] | None = None,
        trusted_origins: list[str] | None = None,
    ) -> None:
        self.app = app
        self.exempt_urls = exempt_urls or []
        self.trusted_origins = frozenset(
            _normalize_origin(o) for o in (trusted_origins or []) if o
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        # Ensure a CSRF token exists in the session.
        session = scope.get("session")
        if session is None:
            # Fail-closed: reject unsafe requests when session is unavailable.
            if request.method not in _SAFE_METHODS:
                logger.error(
                    "csrf.no_session",
                    extra={
                        "path": request.url.path,
                        "method": request.method,
                    },
                )
                response = PlainTextResponse(
                    "CSRF check failed — session unavailable", status_code=403
                )
                await response(scope, receive, send)
                return
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

        # --- Defence-in-depth: Origin / Referer verification ---
        if self.trusted_origins and not self._check_origin(request):
            logger.warning(
                "csrf.origin_rejected",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "origin": request.headers.get("origin", ""),
                    "referer": request.headers.get("referer", ""),
                },
            )
            response = self._error_response(request)
            await response(scope, receive, send)
            return

        # --- Primary check: Synchronizer token ---
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_origin(self, request: Request) -> bool:
        """Verify that Origin or Referer matches a trusted origin."""
        origin = request.headers.get("origin")
        if origin:
            return _normalize_origin(origin) in self.trusted_origins

        referer = request.headers.get("referer")
        if referer:
            parsed = urlparse(referer)
            referer_origin = f"{parsed.scheme}://{parsed.netloc}"
            return _normalize_origin(referer_origin) in self.trusted_origins

        # Neither header present — allow through but log for visibility.
        # Privacy proxies and extensions may strip these headers; the
        # synchronizer token still protects against CSRF in this case.
        logger.info(
            "csrf.no_origin_header",
            extra={
                "path": request.url.path,
                "method": request.method,
            },
        )
        return True

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
