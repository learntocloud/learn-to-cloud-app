"""One-off script to generate favicon.ico and apple-touch-icon.png from favicon.svg."""

import struct
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    static_dir = Path(__file__).parent.parent / "static"
    svg_path = static_dir / "favicon.svg"

    if not svg_path.exists():
        raise FileNotFoundError(f"SVG not found: {svg_path}")

    apple_icon = static_dir / "apple-touch-icon.png"
    subprocess.run(
        [
            "rsvg-convert",
            "-w",
            "180",
            "-h",
            "180",
            str(svg_path),
            "-o",
            str(apple_icon),
        ],
        check=True,
    )
    print(f"Created {apple_icon} ({apple_icon.stat().st_size} bytes)")

    sizes = [16, 32, 48]
    png_data: list[tuple[int, bytes]] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for size in sizes:
            tmp_png = Path(tmpdir) / f"favicon-{size}.png"
            subprocess.run(
                [
                    "rsvg-convert",
                    "-w",
                    str(size),
                    "-h",
                    str(size),
                    str(svg_path),
                    "-o",
                    str(tmp_png),
                ],
                check=True,
            )
            png_data.append((size, tmp_png.read_bytes()))

    num_images = len(png_data)
    header = struct.pack("<HHH", 0, 1, num_images)  # reserved=0, type=1(ICO), count

    dir_entry_size = 16
    data_offset = 6 + dir_entry_size * num_images

    directory = b""
    image_data = b""
    for size, raw in png_data:
        w = size if size < 256 else 0
        h = size if size < 256 else 0
        directory += struct.pack(
            "<BBBBHHII",
            w,  # width (0 = 256)
            h,  # height (0 = 256)
            0,  # color palette count
            0,  # reserved
            1,  # color planes
            32,  # bits per pixel
            len(raw),  # data size
            data_offset,  # offset from start of file
        )
        data_offset += len(raw)
        image_data += raw

    ico_path = static_dir / "favicon.ico"
    ico_path.write_bytes(header + directory + image_data)
    print(f"Created {ico_path} ({ico_path.stat().st_size} bytes)")

    from PIL import Image

    ico = Image.open(ico_path)
    print(f"ICO sizes: {ico.info.get('sizes')}")


if __name__ == "__main__":
    main()
