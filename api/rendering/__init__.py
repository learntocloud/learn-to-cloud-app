"""Rendering module for presentation concerns.

This module handles all presentation/rendering logic:
- Certificate SVG generation
- PDF conversion
- Visual formatting

This separates presentation concerns from business logic in services.
"""

from .certificates import (
    generate_certificate_svg,
    svg_to_base64_data_uri,
    svg_to_pdf,
)

__all__ = [
    "generate_certificate_svg",
    "svg_to_base64_data_uri",
    "svg_to_pdf",
]
