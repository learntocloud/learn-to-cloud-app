"""Quick script to test certificate rendering locally (no DB, no auth).

Run from the api/ directory:
    python scripts/test_certificate.py

Outputs:
    scripts/test_cert.svg
    scripts/test_cert.pdf  (requires cairosvg)
    scripts/test_cert.png  (requires cairosvg)
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure the api package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rendering.certificates import generate_certificate_svg

OUTPUT_DIR = Path(__file__).resolve().parent


def main() -> None:
    svg = generate_certificate_svg(
        recipient_name="Gwyneth Test",
        verification_code="LTC-abc123-test",
        issued_at=datetime.now(UTC),
        phases_completed=5,
        total_phases=5,
    )

    svg_path = OUTPUT_DIR / "test_cert.svg"
    svg_path.write_text(svg, encoding="utf-8")
    print(f"SVG saved to {svg_path}")

    try:
        import cairosvg

        pdf_path = OUTPUT_DIR / "test_cert.pdf"
        cairosvg.svg2pdf(bytestring=svg.encode(), write_to=str(pdf_path))
        print(f"PDF saved to {pdf_path}")

        png_path = OUTPUT_DIR / "test_cert.png"
        cairosvg.svg2png(bytestring=svg.encode(), write_to=str(png_path), scale=2)
        print(f"PNG saved to {png_path}")
    except ImportError:
        print(
            "cairosvg not installed — skipping PDF/PNG."
            " Install with: pip install cairosvg"
        )
    except Exception as e:
        print(f"PDF/PNG generation failed: {e}")
        print("This usually means GTK/Cairo libraries aren't installed on Windows.")
        print("The SVG file is still valid — open it in a browser to preview.")


if __name__ == "__main__":
    main()
