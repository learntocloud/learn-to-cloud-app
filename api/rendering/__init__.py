"""Rendering module for presentation concerns.

This module handles all presentation/rendering logic:
- Certificate SVG generation
- PDF conversion
- Step data conversion for templates
- Visual formatting

This separates presentation concerns from business logic in services.
"""

from rendering.certificates import (
    generate_certificate_svg,
    svg_to_base64_data_uri,
    svg_to_pdf,
)
from rendering.steps import build_step_data, render_md

__all__ = [
    "build_step_data",
    "generate_certificate_svg",
    "render_md",
    "svg_to_base64_data_uri",
    "svg_to_pdf",
]
