"""Generate the 1200x630 social-share cards (web/social/*.png) and web/favicon.ico from pages.json.

Run:  python tools/make_social_images.py
Needs Pillow. Fonts: Inter if installed, otherwise DejaVu Sans (any bold sans TTF/OTF works).
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
W, H = 1200, 630
BG, INK, MUTED, ACCENT = (246, 245, 242), (24, 28, 36), (96, 104, 118), (42, 120, 214)
FONTS = ["/usr/share/fonts/opentype/inter/Inter-Bold.otf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
REG = ["/usr/share/fonts/opentype/inter/Inter-Regular.otf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def font(paths, size):
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def card(title: str, subtitle: str, out: Path) -> None:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 18, H], fill=ACCENT)
    icon = Image.open(WEB / "icons" / "icon-192.png").convert("RGBA").resize((96, 96))
    im.paste(icon, (80, 70), icon)
    d.text((196, 96), "RetailPulse", font=font(FONTS, 44), fill=INK)
    y = 230
    for line in textwrap.wrap(title, 24)[:3]:
        d.text((80, y), line, font=font(FONTS, 76), fill=INK)
        y += 92
    y += 14
    for line in textwrap.wrap(subtitle, 58)[:3]:
        d.text((80, y), line, font=font(REG, 32), fill=MUTED)
        y += 44
    d.text((80, H - 70), "Synthetic data  |  github.com/Nikhil-creat/RetailPulse", font=font(REG, 26), fill=MUTED)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, optimize=True)


def main() -> None:
    data = json.loads((WEB / "pages.json").read_text(encoding="utf-8"))
    for p in data["pages"]:
        card(p["h1"], data["site"]["tagline"] if p["key"] == "overview" else p["description"], WEB / p["social"])
    base = Image.open(WEB / "icons" / "icon-512.png").convert("RGBA")
    base.save(WEB / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    print("wrote", len(data["pages"]), "social cards and favicon.ico")


if __name__ == "__main__":
    main()
