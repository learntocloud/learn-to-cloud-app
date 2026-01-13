"""Certificate generation utilities for Learn to Cloud."""

import base64
import hashlib
import re
import secrets
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

# Certificate configuration
CERTIFICATE_TITLE = "Learn to Cloud"
CERTIFICATE_SUBTITLE = "Certificate of Completion"
ISSUER_NAME = "Learn to Cloud"
ISSUER_URL = "https://learntocloud.guide"

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
_LOGO_SVG_PATH = _ASSETS_DIR / "Logo-03.svg"


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

    # Find the outer <svg ...> ... </svg> wrapper.
    open_tag_match = re.search(r"<svg\b[^>]*>", logo_svg, flags=re.IGNORECASE | re.DOTALL)
    close_tag_index = logo_svg.lower().rfind("</svg>")
    if not open_tag_match or close_tag_index == -1:
        return None

    svg_open_tag = open_tag_match.group(0)
    inner = logo_svg[open_tag_match.end() : close_tag_index]

    view_box_match = re.search(r'\bviewBox="([^"]+)"', svg_open_tag)
    view_box = view_box_match.group(1) if view_box_match else "0 0 800 600"

    # Strip scripts defensively.
    inner = re.sub(r"<script\b[^>]*>.*?</script>", "", inner, flags=re.IGNORECASE | re.DOTALL)

    # The exported logo wordmark uses a dark blue fill that can be hard to see on
    # the certificate's black background. Recolor the primary wordmark class to
    # use a bright blue gradient visible on black.
    inner = re.sub(
      r"\.st0\{fill:\s*#124D99;\}",
      ".st0{fill:url(#ltcLogoTextGradient);}",
      inner,
      flags=re.IGNORECASE,
    )

    # Prefix IDs to avoid collisions with certificate defs (SVG IDs are document-global).
    prefix = "ltcLogo-"
    ids = set(re.findall(r'\bid="([^"]+)"', inner))
    for old_id in sorted(ids, key=len, reverse=True):
        new_id = f"{prefix}{old_id}"
        inner = inner.replace(f'id="{old_id}"', f'id="{new_id}"')
        inner = inner.replace(f"url(#{old_id})", f"url(#{new_id})")
        inner = inner.replace(f'href="#{old_id}"', f'href="#{new_id}"')
        inner = inner.replace(f'xlink:href="#{old_id}"', f'xlink:href="#{new_id}"')

    # Add gradient definition inside the nested SVG (nested SVGs can't reference parent defs)
    gradient_def = """<defs>
      <linearGradient id="ltcLogoTextGradient" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0" stop-color="#83DCFF"/>
        <stop offset="1" stop-color="#0076F7"/>
      </linearGradient>
    </defs>"""

    # Positioned/sized for the 800x600 certificate viewBox.
    return (
        f'<svg x="280" y="40" width="240" height="130" '
        f'viewBox="{view_box}" preserveAspectRatio="xMidYMid meet">{gradient_def}{inner}</svg>'
    )

# Phase information for certificates
PHASE_INFO = {
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


def generate_verification_code(user_id: str, certificate_type: str) -> str:
    """Generate a unique, verifiable certificate code.

    Format: LTC-{hash}-{random}
    The hash includes user_id, certificate_type, and timestamp for uniqueness.
    """
    timestamp = datetime.now(UTC).isoformat()
    data = f"{user_id}:{certificate_type}:{timestamp}"
    hash_part = hashlib.sha256(data.encode()).hexdigest()[:12].upper()
    random_part = secrets.token_hex(4).upper()
    return f"LTC-{hash_part}-{random_part}"


def get_certificate_info(certificate_type: str) -> dict:
    """Get display information for a certificate type."""
    return PHASE_INFO.get(certificate_type, PHASE_INFO["full_completion"])


def generate_certificate_svg(
    recipient_name: str,
    certificate_type: str,
    verification_code: str,
    issued_at: datetime,
    topics_completed: int,
    total_topics: int,
) -> str:
    """Generate an SVG certificate.

    Returns the SVG as a string that can be rendered or converted to PDF.
    """
    cert_info = get_certificate_info(certificate_type)
    issued_date = issued_at.strftime("%B %d, %Y")

    # Escape any special characters in the name
    safe_name = (
        recipient_name.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

    logo_inline_svg = _get_logo_inline_svg()
    logo_block = ""
    if logo_inline_svg:
        logo_block = f"""
  <!-- Brand logo (Logo-03.svg) -->
  <g filter="url(#logoGlow)">
    {logo_inline_svg}
  </g>
"""

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

    <!-- Glow effect for logo -->
    <filter id="logoGlow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="8" result="blur"/>
      <feFlood flood-color="#0076F7" flood-opacity="0.4"/>
      <feComposite in2="blur" operator="in"/>
      <feMerge>
        <feMergeNode/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>

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
  <text x="400" y="195" font-family="Arial, Helvetica, sans-serif" font-size="10" fill="#4b5563" text-anchor="middle" letter-spacing="4" font-weight="500">
    CERTIFICATE OF COMPLETION
  </text>

  <!-- Recipient name with glow -->
  <text x="400" y="280" font-family="Georgia, Times, serif" font-size="48" fill="#ffffff" text-anchor="middle" font-weight="bold" filter="url(#nameGlow)">
    {safe_name}
  </text>

  <!-- Achievement name -->
  <text x="400" y="360" font-family="Arial, Helvetica, sans-serif" font-size="24" fill="url(#blueGradientV)" text-anchor="middle" font-weight="bold">
    {cert_info["name"]}
  </text>
  
  <!-- Achievement description -->
  <text x="400" y="395" font-family="Arial, Helvetica, sans-serif" font-size="13" fill="#64748b" text-anchor="middle">
    {cert_info["description"]}
  </text>

  <!-- Achievement seal -->
  <g transform="translate(680, 480)" filter="url(#sealGlow)">
    <circle cx="0" cy="0" r="45" fill="none" stroke="url(#blueGradient)" stroke-width="2" opacity="0.8"/>
    <circle cx="0" cy="0" r="38" fill="none" stroke="url(#blueGradient)" stroke-width="1" opacity="0.5"/>
    <!-- Checkmark as path for better PDF compatibility -->
    <path d="M-8 -4 L-3 2 L8 -10" fill="none" stroke="url(#blueGradient)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
    <text x="0" y="12" font-family="Arial, Helvetica, sans-serif" font-size="9" fill="#83DCFF" text-anchor="middle" font-weight="600">
      {topics_completed}/{total_topics}
    </text>
    <text x="0" y="24" font-family="Arial, Helvetica, sans-serif" font-size="7" fill="#64748b" text-anchor="middle">
      COMPLETE
    </text>
  </g>

  <!-- Date and verification section -->
  <g transform="translate(0, 500)">
    <!-- Date -->
    <g transform="translate(150, 0)">
      <text x="0" y="0" font-family="Arial, Helvetica, sans-serif" font-size="9" fill="#4b5563" text-anchor="middle" letter-spacing="2">
        ISSUED
      </text>
      <text x="0" y="24" font-family="Georgia, Times, serif" font-size="16" fill="#e5e7eb" text-anchor="middle">
        {issued_date}
      </text>
    </g>

    <!-- Verification Code -->
    <g transform="translate(400, 0)">
      <text x="0" y="0" font-family="Arial, Helvetica, sans-serif" font-size="9" fill="#4b5563" text-anchor="middle" letter-spacing="2">
        VERIFICATION
      </text>
      <text x="0" y="24" font-family="monospace" font-size="13" fill="#83DCFF" text-anchor="middle" font-weight="600">
        {verification_code}
      </text>
    </g>
  </g>

  <!-- Footer with verification URL -->
  <text x="400" y="568" font-family="Arial, Helvetica, sans-serif" font-size="9" fill="#374151" text-anchor="middle">
    Verify at {ISSUER_URL}/verify/{verification_code}
  </text>
</svg>"""

    return svg


def svg_to_base64_data_uri(svg_content: str) -> str:
    """Convert SVG string to base64 data URI for embedding."""
    encoded = base64.b64encode(svg_content.encode("utf-8")).decode("utf-8")
    return f"data:image/svg+xml;base64,{encoded}"


# Total topics per phase (should match frontend content)
PHASE_TOPIC_COUNTS = {
    0: 6,  # phase0
    1: 6,  # phase1
    2: 7,  # phase2
    3: 9,  # phase3
    4: 6,  # phase4
    5: 6,  # phase5
}

TOTAL_TOPICS = sum(PHASE_TOPIC_COUNTS.values())  # 40 total


def get_completion_requirements(certificate_type: str) -> dict:
    """Get the completion requirements for a certificate type.

    Returns dict with:
    - required_phases: list of phase IDs that must be completed
    - min_completion_percentage: minimum percentage (0-100) required

    Note: Only full_completion is supported. Phase achievements are tracked via badges.
    """
    if certificate_type == "full_completion":
        return {
            "required_phases": [0, 1, 2, 3, 4, 5],
            "min_completion_percentage": 100,  # Must complete everything
        }
    else:
        raise ValueError(
            f"Unknown certificate type: {certificate_type}. "
            "Only 'full_completion' is supported. Phase achievements are tracked via badges."
        )


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
