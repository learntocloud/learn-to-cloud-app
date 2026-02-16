"""Legacy /phaseN URL redirect middleware.

Pure ASGI middleware — the path-resolution callable is injected at
construction time so ``core`` never imports from ``services``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


class LegacyPhaseRedirectMiddleware:
    """Redirect legacy /phaseN URLs to canonical /phase/N URLs (308 Permanent).

    Registered as the outermost middleware so redirects are served before
    session or user-tracking middleware run — avoids creating sessions and
    tracking users for requests that will immediately redirect.

    Args:
        app: The next ASGI application in the middleware stack.
        resolver: A callable ``(path: str) -> str | None`` that returns
            the canonical redirect target or ``None`` if no redirect is needed.
    """

    def __init__(
        self,
        app: ASGIApp,
        resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        self.app = app
        self._resolve = resolver or (lambda path: None)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]
        try:
            target_path = self._resolve(path)
        except Exception:
            logger.exception("legacy_url.resolve_error", extra={"path": path})
            target_path = None

        if target_path is not None and target_path != path:
            query = scope.get("query_string", b"").decode("latin-1")
            target_url = target_path if not query else f"{target_path}?{query}"
            logger.info(
                "legacy_url.redirect",
                extra={
                    "from_path": path,
                    "to_path": target_path,
                    "has_query": bool(query),
                    "query_length": len(query),
                    "status_code": 308,
                },
            )
            response = RedirectResponse(url=target_url, status_code=308)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
