"""Jinja2 template engine — shared across routes and exception handlers.

Provides a module-level ``templates`` instance so route files can import
it directly instead of reaching through ``request.app.state``.  This
matches the pattern shown in the official FastAPI template docs.

Static-file cache-busting is handled via a context processor that injects
``static_url`` into every template render.
"""

import hashlib
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
_static_dir = Path(__file__).resolve().parent.parent / "static"

_static_hashes: dict[str, str] = {}


def _build_static_file_hashes(static_dir: Path) -> dict[str, str]:
    """Compute short content hashes for static files (cache-busting)."""
    hashes: dict[str, str] = {}
    if not static_dir.exists():
        return hashes
    for file_path in static_dir.rglob("*"):
        if file_path.is_file():
            rel = file_path.relative_to(static_dir).as_posix()
            digest = hashlib.md5(
                file_path.read_bytes(), usedforsecurity=False
            ).hexdigest()[:8]
            hashes[rel] = digest
    return hashes


def static_url(path: str) -> str:
    """Return a cache-busted static URL, e.g. /static/css/styles.css?v=a1b2c3d4."""
    version = _static_hashes.get(path, "")
    if version:
        return f"/static/{path}?v={version}"
    return f"/static/{path}"


def _static_url_context(request: Request) -> dict[str, object]:
    """Context processor that injects ``static_url`` into every template."""
    return {"static_url": static_url}


# Populate hashes at import time
if _static_dir.exists():
    _static_hashes.update(_build_static_file_hashes(_static_dir))

templates = Jinja2Templates(
    directory=str(_templates_dir),
    context_processors=[_static_url_context],
)
