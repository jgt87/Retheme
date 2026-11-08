"""Regenerate the README screenshots in docs/screenshots/.

Drives the real UI with the fictional "Lumen & Co." template (never a real
company's branding: the screenshots are public) and the bundled demo deck.

    pip install -r requirements-dev.txt
    python scripts/screenshots.py [--channel msedge]
"""

from __future__ import annotations

import argparse
import io
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from e2e.flow import running_server, walk  # noqa: E402
from tests.fixtures.lumen_template import build  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
# surface -> (file name, crop height in px; None = whole page)
SHOTS = {"review": ("extract-review.png", 1340),
         "choices": ("retheme-choices.png", 1620),
         "result": ("preview-export.png", 1140)}


def _save(png: bytes, name: str, crop_h: int | None) -> None:
    im = Image.open(io.BytesIO(png)).convert("RGB")
    if crop_h:
        im = im.crop((0, 0, im.width, min(crop_h, im.height)))
    im.save(OUT / name, optimize=True)
    print(f"  {name} {im.size[0]}x{im.size[1]}")


def _gallery(slides: list[Image.Image], cols: int = 3, rows: int = 2,
             tile_w: int = 440, gap: int = 16) -> Image.Image:
    picks = slides[: cols * rows]
    tile_h = round(picks[0].height * tile_w / picks[0].width)
    sheet = Image.new("RGB", (cols * tile_w + (cols + 1) * gap,
                              rows * tile_h + (rows + 1) * gap), (238, 240, 244))
    for i, im in enumerate(picks):
        r, c = divmod(i, cols)
        sheet.paste(im.resize((tile_w, tile_h), Image.LANCZOS),
                    (gap + c * (tile_w + gap), gap + r * (tile_h + gap)))
    return sheet


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--channel", default=None,
                    help="browser channel, e.g. msedge or chrome (default: bundled chromium)")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    template = build(Path(tempfile.mkdtemp()) / "lumen-template.pptx")

    with running_server() as url, sync_playwright() as p:
        browser = p.chromium.launch(channel=args.channel)
        page = browser.new_page(viewport={"width": 1400, "height": 900},
                                color_scheme="light", reduced_motion="reduce")

        def shoot(surface: str) -> None:
            if surface in SHOTS:
                name, crop = SHOTS[surface]
                _save(page.screenshot(full_page=True), name, crop)
            if surface == "result":
                frame = page.frame_locator("#preview-frame")
                slides = [Image.open(io.BytesIO(frame.locator(".slide").nth(i).screenshot()))
                          .convert("RGB") for i in range(frame.locator(".slide").count())]
                sheet = _gallery(slides)
                sheet.save(OUT / "rethemed-deck.png", optimize=True)
                print(f"  rethemed-deck.png {sheet.size[0]}x{sheet.size[1]}")

        walk(page, url, template, shoot)
        browser.close()


if __name__ == "__main__":
    main()
