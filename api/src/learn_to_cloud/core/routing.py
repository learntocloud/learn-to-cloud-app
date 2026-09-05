"""Response policies for browser page routes."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.responses import RedirectResponse
from fastapi.routing import APIRoute

from learn_to_cloud.core.auth import AuthenticationRequired


class LoginRedirectRoute(APIRoute):
    """Redirect unauthenticated page navigation to login, keeping HTMX errors."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await handler(request)
            except AuthenticationRequired:
                if request.headers.get("hx-request") == "true":
                    raise
                return RedirectResponse("/auth/login", status_code=303)

        return handle
