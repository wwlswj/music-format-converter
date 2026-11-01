"""Generate the project PNG and ICO icons without external artwork."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def _gradient(size: int) -> Image.Image:
    """Draw a deep-blue vertical gradient background."""
    image = Image.new("RGBA", (size, size), "#173B57")
    pixels = image.load()
    start = (23, 59, 87)
    end = (45, 106, 138)
    for y in range(size):
        ratio = y / max(1, size - 1)
        color = tuple(
            round(a + (b - a) * ratio)
            for a, b in zip(start, end, strict=True)
        )
        for x in range(size):
            pixels[x, y] = (*color, 255)
    return image


def main() -> int:
    """Create icon assets under the repository assets directory."""
    root = Path(__file__).resolve().parents[1]
    size = 256
    image = _gradient(size)
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle((8, 8, 248, 248), radius=52, fill=(23, 59, 87, 255))
    draw.ellipse((54, 54, 202, 202), fill=(226, 184, 78, 255))
    draw.ellipse((91, 78, 166, 153), outline=(23, 59, 87, 255), width=11)
    draw.rectangle((143, 102, 156, 187), fill=(23, 59, 87, 255))
    draw.polygon(
        [(156, 102), (191, 91), (191, 147), (174, 151), (174, 114), (156, 120)],
        fill=(23, 59, 87, 255),
    )
    draw.ellipse((116, 171, 172, 207), fill=(23, 59, 87, 255))
    image.save(root / "assets" / "icon.png", format="PNG")
    image.save(
        root / "assets" / "icon.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

