"""Jinja2 template engine — shared across routes and exception handlers.

Provides a module-level ``templates`` instance so route files can import
it directly instead of reaching through ``request.app.state``.  This
matches the pattern shown in the official FastAPI template docs.

The Jinja2 environment globals (e.g. ``static_url``) are added at
app startup in ``main.py`` after the static-file hashes are computed.
"""

from pathlib import Path

from fastapi.templating import Jinja2Templates

_templates_dir = Path(__file__).resolve().parent.parent / "templates"

templates = Jinja2Templates(directory=str(_templates_dir))
