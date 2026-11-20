"""Generate lightweight, clearly illustrative macro-news cover art."""

from __future__ import annotations

import hashlib
import unicodedata
from io import BytesIO

from PIL import Image, ImageDraw


CANVAS = (960, 420)
THEME_STYLES = {
    "Bolsas & tecnologia": ((11, 21, 31), (28, 112, 130), (69, 212, 176)),
    "Juros & Fed": ((17, 23, 36), (66, 83, 135), (121, 172, 245)),
    "Brasil": ((15, 31, 28), (35, 120, 82), (245, 197, 66)),
    "Geopolítica": ((31, 23, 28), (134, 58, 62), (238, 147, 103)),
    "Energia & commodities": ((28, 27, 21), (125, 87, 38), (242, 190, 79)),
    "Cripto": ((25, 21, 38), (105, 70, 154), (191, 151, 255)),
    "China & comércio": ((33, 23, 24), (158, 59, 49), (239, 187, 84)),
    "Inflação & atividade": ((26, 29, 34), (73, 99, 124), (109, 205, 214)),
    "Crédito & risco": ((28, 22, 33), (111, 61, 104), (225, 123, 172)),
    "Panorama macro": ((18, 25, 34), (51, 91, 113), (92, 190, 197)),
}


def _seed(theme: str, item_id: str) -> int:
    digest = hashlib.sha256(f"{theme}|{item_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def generate_macro_news_art(theme: str, item_id: str = "") -> bytes:
    """Return a deterministic PNG cover based on the story's macro theme."""
    import random

    theme = theme if theme in THEME_STYLES else "Panorama macro"
    background, mid, accent = THEME_STYLES[theme]
    rng = random.Random(_seed(theme, item_id))
    image = Image.new("RGB", CANVAS, background)
    draw = ImageDraw.Draw(image, "RGBA")

    # A restrained editorial market-board motif, varied per headline.
    for x in range(0, CANVAS[0], 48):
        draw.line((x, 0, x, CANVAS[1]), fill=(180, 205, 220, 14), width=1)
    for y in range(0, CANVAS[1], 48):
        draw.line((0, y, CANVAS[0], y), fill=(180, 205, 220, 14), width=1)

    draw.ellipse((590, -150, 1100, 360), fill=(*mid, 125))
    draw.ellipse((690, -70, 1010, 250), outline=(*accent, 135), width=3)
    draw.ellipse((735, -25, 965, 205), outline=(*accent, 75), width=2)

    points = []
    y = rng.randint(185, 285)
    for x in range(20, 940, 28):
        y = max(90, min(365, y + rng.randint(-32, 32)))
        points.append((x, y))
    draw.line(points, fill=(*accent, 220), width=5, joint="curve")
    for x, y in points[::4]:
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(*accent, 235))

    for i in range(9):
        x = 560 + i * 37
        height = rng.randint(36, 150)
        y0 = 350 - height
        draw.rounded_rectangle((x, y0, x + 15, 350), radius=3, fill=(*accent, 55 + i * 10))

    # The topic stamp labels this as an illustration, never as a news photograph.
    draw.rounded_rectangle((30, 28, 440, 69), radius=7, fill=(6, 11, 18, 205), outline=(*accent, 210), width=2)
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    stamp = unicodedata.normalize("NFKD", f"{theme.upper()}  /  ILUSTRACAO EDITORIAL").encode("ascii", "ignore").decode("ascii")
    draw.text((45, 40), stamp[:42], font=font, fill=(240, 245, 250, 255))

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
