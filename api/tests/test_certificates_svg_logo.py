from datetime import UTC, datetime

from shared.certificates import generate_certificate_svg


def test_certificate_svg_inlines_brand_logo() -> None:
    svg = generate_certificate_svg(
        recipient_name="Gwyneth",
        certificate_type="full_completion",
        verification_code="LTC-TEST-LOGO",
        issued_at=datetime(2026, 1, 13, tzinfo=UTC),
        topics_completed=40,
        total_topics=40,
    )

    # Inline <svg> is the most reliable way to embed an SVG logo.
    assert "Brand logo (Logo-03.svg)" in svg
    assert '<svg x="280" y="40"' in svg

    # Ensure we don't regress back to <image href="data:image/svg+xml...">,
    # which is often blocked by browsers/viewers.
    assert "<image" not in svg

    # The inliner prefixes IDs to avoid collisions with certificate defs.
    assert "ltcLogo-" in svg

    # The .st0 class (dark blue text) should be recolored to use a local gradient
    # (nested SVGs can't reference parent defs) so it's visible on black background.
    assert "ltcLogoTextGradient" in svg
    assert ".st0{fill:url(#ltcLogoTextGradient);}" in svg
    # Original dark blue fill should NOT remain
    assert ".st0{fill:#124D99;}" not in svg
