"""Layout preview rendering for the review UI.

Preferred pipeline (spec §3.6): LibreOffice headless -> PDF -> PNG.
When LibreOffice (or a PDF rasterizer) is unavailable, falls back to
schematic previews drawn with Pillow from the extracted data itself —
background color, placeholder boxes, asset outlines — which is still enough
to spot misclassified assets and wrong positions during review.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PREVIEW_WIDTH = 960

_SOFFICE_CANDIDATES = [
    "soffice",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
]


def find_soffice() -> str | None:
    for candidate in _SOFFICE_CANDIDATES:
        path = shutil.which(candidate) or (candidate if Path(candidate).is_file() else None)
        if path:
            return path
    return None


# ------------------------------------------------- LibreOffice pipeline

def render_previews_soffice(pptx_path: Path, layout_names: list[str],
                            out_dir: Path) -> bool:
    """Build a deck with one blank slide per layout, convert via LibreOffice
    to PDF, rasterize each page. Returns True on success."""
    soffice = find_soffice()
    if not soffice:
        return False
    try:
        import pypdfium2  # optional dependency
    except ImportError:
        return False

    from pptx import Presentation

    from .extract import _as_presentation

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        # .potx/.ppsx need their content type patched before python-pptx
        # will open them (same handling as the main extraction path)
        prs = Presentation(str(_as_presentation(pptx_path, tmp_dir)))
        # drop existing slides, add one per layout
        xml_slides = prs.slides._sldIdLst
        for sld in list(xml_slides):
            xml_slides.remove(sld)
        ordered = []
        for master in prs.slide_masters:
            for layout in master.slide_layouts:
                prs.slides.add_slide(layout)
                ordered.append(layout.name)
        deck_path = tmp_dir / "layouts.pptx"
        prs.save(str(deck_path))

        result = subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf",
             "--outdir", str(tmp_dir), str(deck_path)],
            capture_output=True, timeout=300)
        pdf_path = tmp_dir / "layouts.pdf"
        if result.returncode != 0 or not pdf_path.exists():
            return False

        pdf = pypdfium2.PdfDocument(str(pdf_path))
        for i, layout_name in enumerate(ordered):
            if i >= len(pdf):
                break
            page = pdf[i]
            bitmap = page.render(scale=PREVIEW_WIDTH / page.get_width())
            img = bitmap.to_pil()
            img.save(out_dir / f"layout-{_slug(layout_name)}.png")
    return True


# --------------------------------------------------- schematic fallback

def _slug(text: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "layout"


def _hex_rgb(hex_str: str) -> tuple[int, int, int]:
    hex_str = (hex_str or "FFFFFF").lstrip("#")
    try:
        return tuple(int(hex_str[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (255, 255, 255)


def render_preview_schematic(layout: dict, assets: dict[str, dict],
                             slide_w_in: float, slide_h_in: float,
                             out_path: Path) -> None:
    w = PREVIEW_WIDTH
    h = round(w * slide_h_in / slide_w_in)
    bg = layout.get("background", {})
    if bg.get("type") == "solid":
        base_color = _hex_rgb(bg.get("hex", "FFFFFF"))
    elif bg.get("type") == "gradient" and bg.get("stops"):
        base_color = _hex_rgb(bg["stops"][0].get("hex", "FFFFFF"))
    else:
        base_color = (240, 240, 240)
    img = Image.new("RGB", (w, h), base_color)
    draw = ImageDraw.Draw(img, "RGBA")

    try:
        font = ImageFont.truetype("arial.ttf", 13)
        font_small = ImageFont.truetype("arial.ttf", 10)
    except OSError:
        font = font_small = ImageFont.load_default()

    def box(pos, size):
        if not pos or not size:
            return None
        return (pos["x_pct"] * w, pos["y_pct"] * h,
                (pos["x_pct"] + size["width_pct"]) * w,
                (pos["y_pct"] + size["height_pct"]) * h)

    # assets first (usually behind), then placeholders
    for asset_id in layout.get("static_assets", []):
        asset = assets.get(asset_id)
        if not asset:
            continue
        b = box(asset.get("position"), asset.get("size"))
        if not b:
            continue
        color = {"logo": (46, 160, 67, 90), "icon": (130, 80, 223, 90),
                 "background_image": (108, 182, 255, 60),
                 }.get(asset.get("type"), (255, 150, 40, 80))
        draw.rectangle(b, fill=color, outline=color[:3] + (220,), width=2)
        draw.text((b[0] + 3, b[1] + 2), f'{asset.get("type", "?")}: {asset_id}',
                  fill=(20, 20, 20, 255), font=font_small)

    for ph in layout.get("placeholders", []):
        b = box(ph.get("position"), ph.get("size"))
        if not b:
            continue
        draw.rectangle(b, outline=(60, 60, 60, 230), width=2)
        lvl1 = ph.get("format_levels", {}).get("1", {})
        label = f'{ph["type"]}'
        if lvl1.get("font") or lvl1.get("size_pt"):
            label += f' · {lvl1.get("font", "")} {lvl1.get("size_pt", "")}pt'
        draw.text((b[0] + 4, b[1] + 3), label, fill=(60, 60, 60, 255), font=font)

    draw.text((6, h - 20), f'{layout["name"]} — schematic preview '
              f'(install LibreOffice + pypdfium2 for rendered previews)',
              fill=(120, 120, 120, 255), font=font_small)
    img.save(out_path)


def render_all_previews(pptx_path: Path, layouts: list[dict],
                        assets: dict[str, dict], slide_w_in: float,
                        slide_h_in: float, previews_dir: Path,
                        notes: list[str] | None = None) -> str:
    """Returns the mode used: 'libreoffice' or 'schematic'. Failures of the
    LibreOffice pipeline are reported via `notes`, not silently swallowed."""
    previews_dir.mkdir(parents=True, exist_ok=True)
    try:
        if render_previews_soffice(pptx_path, [l["name"] for l in layouts],
                                   previews_dir):
            return "libreoffice"
    except Exception as exc:
        if notes is not None:
            notes.append(f"LibreOffice preview pipeline failed "
                         f"({type(exc).__name__}: {exc}); "
                         f"using schematic previews.")
    for layout in layouts:
        out = previews_dir / f'layout-{_slug(layout["name"])}.png'
        render_preview_schematic(layout, assets, slide_w_in, slide_h_in, out)
    return "schematic"
