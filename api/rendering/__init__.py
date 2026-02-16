"""Rendering module for presentation concerns.

This module handles all presentation/rendering logic:
- Step data conversion for templates
- Visual formatting

This separates presentation concerns from business logic in services.
"""

from rendering.steps import build_step_data, render_md

__all__ = [
    "build_step_data",
    "render_md",
]
