"""Certificate rendering - SVG and PDF generation.

This module handles the visual/presentation aspects of certificates:
- SVG template rendering
- PDF conversion
- Visual styling and formatting

This is separated from certificate business logic (eligibility, creation, verification)
which remains in services/certificates.py.
"""

import base64
import html
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

CERTIFICATE_TITLE = "Learn to Cloud"
CERTIFICATE_SUBTITLE = "Certificate of Completion"
ISSUER_NAME = "Learn to Cloud"
ISSUER_URL = "https://learntocloud.guide"

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
_LOGO_SVG_PATH = _ASSETS_DIR / "Logo-03.svg"


class PhaseInfo(TypedDict):
    """Type for phase display information."""

    name: str
    description: str


PHASE_DISPLAY_INFO: dict[str, PhaseInfo] = {
    "phase_0": {
        "name": "Starting from Zero",
        "description": "IT Fundamentals & Cloud Overview",
    },
    "phase_1": {
        "name": "Linux & Bash",
        "description": "Command Line, Version Control & Infrastructure Basics",
    },
    "phase_2": {
        "name": "Programming & APIs",
        "description": "Python, FastAPI, Databases & AI Integration",
    },
    "phase_3": {
        "name": "Cloud Platform Fundamentals",
        "description": "VMs, Networking, Security & Deployment",
    },
    "phase_4": {
        "name": "DevOps & Containers",
        "description": "Docker, CI/CD, Kubernetes & Monitoring",
    },
    "phase_5": {
        "name": "Cloud Security",
        "description": "IAM, Data Protection & Threat Detection",
    },
    "full_completion": {
        "name": "Full Program Completion",
        "description": "All Phases of Learn to Cloud",
    },
}


@lru_cache(maxsize=1)
def _get_logo_inline_svg() -> str | None:
    """Return a self-contained inline SVG block for the brand logo.

    Why inline instead of <image href="data:image/svg+xml;base64,...">?
    Some browsers/viewers refuse to render nested SVG images for security reasons,
    which makes the logo disappear in previews and downloaded files.

    This function extracts the inner SVG markup, removes scripts, and prefixes IDs
    to avoid collisions with the certificate's own defs.
    """

    try:
        logo_svg = _LOGO_SVG_PATH.read_text(encoding="utf-8")
    except OSError:
        return None

    if not logo_svg.strip():
        return None

    open_tag_match = re.search(
        r"<svg\b[^>]*>", logo_svg, flags=re.IGNORECASE | re.DOTALL
    )
    close_tag_index = logo_svg.lower().rfind("</svg>")
    if not open_tag_match or close_tag_index == -1:
        return None

    svg_open_tag = open_tag_match.group(0)
    inner = logo_svg[open_tag_match.end() : close_tag_index]

    view_box_match = re.search(r'\bviewBox="([^"]+)"', svg_open_tag)
    view_box = view_box_match.group(1) if view_box_match else "0 0 800 600"

    inner = re.sub(
        r"<script\b[^>]*>.*?</script>", "", inner, flags=re.IGNORECASE | re.DOTALL
    )

    inner = re.sub(
        r"\.st0\{fill:\s*#124D99;\}",
        ".st0{fill:url(#ltcLogoTextGradient);}",
        inner,
        flags=re.IGNORECASE,
    )

    prefix = "ltcLogo-"
    ids = set(re.findall(r'\bid="([^"]+)"', inner))
    for old_id in sorted(ids, key=len, reverse=True):
        new_id = f"{prefix}{old_id}"
        inner = inner.replace(f'id="{old_id}"', f'id="{new_id}"')
        inner = inner.replace(f"url(#{old_id})", f"url(#{new_id})")
        inner = inner.replace(f'href="#{old_id}"', f'href="#{new_id}"')
        inner = inner.replace(f'xlink:href="#{old_id}"', f'xlink:href="#{new_id}"')

    # Some renderers are picky about paint servers (gradients) being declared
    # outside a <defs> block, especially when an SVG is nested/embedded.
    # The Logo-03.svg asset declares gradients directly under <g>, which can
    # render as black in some browser contexts when inlined.
    gradient_blocks: list[str] = []

    gradient_pattern = re.compile(
        r"<(linearGradient|radialGradient)\b[^>]*>.*?</\1>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in gradient_pattern.finditer(inner):
        gradient_blocks.append(match.group(0))
    if gradient_blocks:
        inner = gradient_pattern.sub("", inner)

    defs_content = """
      <linearGradient id="ltcLogoTextGradient" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0" stop-color="#83DCFF"/>
        <stop offset="1" stop-color="#0076F7"/>
      </linearGradient>
    """.strip()

    if gradient_blocks:
        defs_content = defs_content + "\n" + "\n".join(gradient_blocks)

    gradient_def = f"<defs>{defs_content}</defs>"

    return (
        f'<svg x="280" y="40" width="240" height="130" '
        f'viewBox="{view_box}" preserveAspectRatio="xMidYMid meet">{gradient_def}{inner}</svg>'
    )


def get_certificate_display_info(certificate_type: str) -> PhaseInfo:
    """Get display information for a certificate type."""
    return PHASE_DISPLAY_INFO.get(
        certificate_type, PHASE_DISPLAY_INFO["full_completion"]
    )


def generate_certificate_svg(
    recipient_name: str,
    certificate_type: str,
    verification_code: str,
    issued_at: datetime,
    phases_completed: int,
    total_phases: int,
) -> str:
    """Generate an SVG certificate.

    Args:
        recipient_name: Name to display on certificate
        certificate_type: Type of certificate
        verification_code: Unique verification code
        issued_at: When certificate was issued
        phases_completed: Number of phases completed
        total_phases: Total number of phases

    Returns:
        SVG content as a string
    """
    cert_info = get_certificate_display_info(certificate_type)
    issued_date = issued_at.strftime("%B %d, %Y")

    safe_name = html.escape(recipient_name, quote=True)

    logo_inline_svg = _get_logo_inline_svg()
    logo_block = ""
    if logo_inline_svg:
        logo_block = f"""
  <!-- Brand logo (Logo-03.svg) -->
  <g>
    {logo_inline_svg}
  </g>
"""

    # Font stacks: Helvetica is a PDF base-14 font (always available in PDF viewers).
    # Times is the serif PDF base-14 font. Courier is the monospace PDF base-14 font.
    # These ensure consistent rendering across all PDF viewers without font embedding.
    sans_font = "Helvetica, Arial, sans-serif"
    serif_font = "Times, 'Times New Roman', Georgia, serif"
    mono_font = "Courier, 'Courier New', monospace"

    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 800 600" width="800" height="600">
  <defs>
    <!-- Blue gradient matching Learn to Cloud brand -->
    <linearGradient id="blueGradient" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0" stop-color="#83DCFF"/>
      <stop offset="1" stop-color="#0076F7"/>
    </linearGradient>

    <!-- Vertical blue gradient for text -->
    <linearGradient id="blueGradientV" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0" stop-color="#83DCFF"/>
      <stop offset="1" stop-color="#0076F7"/>
    </linearGradient>

    <!-- Subtle radial gradient for background depth -->
    <radialGradient id="bgGradient" cx="50%" cy="40%" r="70%">
      <stop offset="0%" stop-color="#0a1628"/>
      <stop offset="100%" stop-color="#000000"/>
    </radialGradient>

    <!-- Subtle glow for name -->
    <filter id="nameGlow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="2" result="blur"/>
      <feFlood flood-color="#ffffff" flood-opacity="0.3"/>
      <feComposite in2="blur" operator="in"/>
      <feMerge>
        <feMergeNode/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>

    <!-- Seal glow -->
    <filter id="sealGlow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="3" result="blur"/>
      <feFlood flood-color="#0076F7" flood-opacity="0.5"/>
      <feComposite in2="blur" operator="in"/>
      <feMerge>
        <feMergeNode/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>

  <!-- Background with subtle gradient -->
  <rect width="800" height="600" fill="url(#bgGradient)"/>

  <!-- Single clean border -->
  <rect x="24" y="24" width="752" height="552" fill="none" stroke="url(#blueGradient)" stroke-width="1.5" rx="4" opacity="0.6"/>

{logo_block}

  <!-- Certificate subtitle -->
  <text x="400" y="195" font-family="{sans_font}" font-size="10" fill="#4b5563" text-anchor="middle" letter-spacing="4" font-weight="500">
    CERTIFICATE OF COMPLETION
  </text>

  <!-- Recipient name with glow -->
  <text x="400" y="280" font-family="{serif_font}" font-size="48" fill="#ffffff" text-anchor="middle" font-weight="bold" filter="url(#nameGlow)">
    {safe_name}
  </text>

  <!-- Achievement name -->
  <text x="400" y="360" font-family="{sans_font}" font-size="24" fill="url(#blueGradientV)" text-anchor="middle" font-weight="bold">
    {cert_info["name"]}
  </text>

  <!-- Achievement description -->
  <text x="400" y="395" font-family="{sans_font}" font-size="13" fill="#64748b" text-anchor="middle">
    {cert_info["description"]}
  </text>

  <!-- Achievement seal -->
  <g transform="translate(680, 480)" filter="url(#sealGlow)">
    <circle cx="0" cy="0" r="45" fill="none" stroke="url(#blueGradient)" stroke-width="2" opacity="0.8"/>
    <circle cx="0" cy="0" r="38" fill="none" stroke="url(#blueGradient)" stroke-width="1" opacity="0.5"/>
    <!-- Checkmark as path for better PDF compatibility -->
    <path d="M-8 -4 L-3 2 L8 -10" fill="none" stroke="url(#blueGradient)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
    <text x="0" y="12" font-family="{sans_font}" font-size="9" fill="#83DCFF" text-anchor="middle" font-weight="600">
      {phases_completed}/{total_phases}
    </text>
    <text x="0" y="24" font-family="{sans_font}" font-size="7" fill="#64748b" text-anchor="middle">
      COMPLETE
    </text>
  </g>

  <!-- Date and verification section -->
  <g transform="translate(0, 500)">
    <!-- Date -->
    <g transform="translate(150, 0)">
      <text x="0" y="0" font-family="{sans_font}" font-size="9" fill="#4b5563" text-anchor="middle" letter-spacing="2">
        ISSUED
      </text>
      <text x="0" y="24" font-family="{serif_font}" font-size="16" fill="#e5e7eb" text-anchor="middle">
        {issued_date}
      </text>
    </g>

    <!-- Verification Code -->
    <g transform="translate(400, 0)">
      <text x="0" y="0" font-family="{sans_font}" font-size="9" fill="#4b5563" text-anchor="middle" letter-spacing="2">
        VERIFICATION
      </text>
      <text x="0" y="24" font-family="{mono_font}" font-size="13" fill="#83DCFF" text-anchor="middle" font-weight="600">
        {verification_code}
      </text>
    </g>
  </g>

  <!-- Footer with verification URL -->
  <text x="400" y="568" font-family="{sans_font}" font-size="9" fill="#374151" text-anchor="middle">
    Verify at {ISSUER_URL}/verify/{verification_code}
  </text>
</svg>"""

    return svg


def svg_to_base64_data_uri(svg_content: str) -> str:
    """Convert SVG string to base64 data URI for embedding."""
    encoded = base64.b64encode(svg_content.encode("utf-8")).decode("utf-8")
    return f"data:image/svg+xml;base64,{encoded}"


def svg_to_pdf(svg_content: str) -> bytes:
    """Convert SVG string to PDF bytes using CairoSVG.

    Args:
        svg_content: SVG string to convert

    Returns:
        PDF content as bytes

    Raises:
        RuntimeError: If cairo library is not installed on the system
    """
    try:
        import cairosvg
    except OSError as e:
        if "cairo" in str(e).lower():
            raise RuntimeError(
                "PDF generation requires the Cairo library. "
                "On macOS: brew install cairo. "
                "On Ubuntu/Debian: apt-get install libcairo2-dev. "
                "On Alpine: apk add cairo-dev."
            ) from e
        raise

    return cairosvg.svg2pdf(bytestring=svg_content.encode("utf-8"))


def svg_to_png(svg_content: str, *, scale: float = 2.0) -> bytes:
    """Convert SVG string to PNG bytes using CairoSVG.

    Useful for browser previews and downloads when SVG rendering differs across
    viewers/browsers.

    Args:
        svg_content: SVG string to convert

    Returns:
        PNG content as bytes

    Raises:
        RuntimeError: If cairo library is not installed on the system
    """
    try:
        import cairosvg
    except OSError as e:
        if "cairo" in str(e).lower():
            raise RuntimeError(
                "PNG generation requires the Cairo library. "
                "On macOS: brew install cairo. "
                "On Ubuntu/Debian: apt-get install libcairo2-dev. "
                "On Alpine: apk add cairo-dev."
            ) from e
        raise

    # Default scale=2.0 renders a 2x raster (e.g. 1600x1200 for an 800x600 SVG),
    # which looks much sharper on high-DPI screens and when downscaled in CSS.
    return cairosvg.svg2png(bytestring=svg_content.encode("utf-8"), scale=scale)
