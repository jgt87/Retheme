"""Phase 2 — Application tool.

Takes a template package (template.json + assets/) and LLM-generated slide
content, produces one HTML file whose slides visually match the template:
fixed-pixel canvas matching the template aspect ratio (the downstream
HTML->PPTX step assumes a fixed slide size), % coordinates inside each slide,
inlined SVG assets, z-order preserved, and auto-shrink overflow handling
with a defined font-size floor.
"""

from __future__ import annotations

import base64
import html
import json
import mimetypes
import re
from pathlib import Path

PX_PER_INCH = 96
FONT_FLOOR_FACTOR = 0.6  # never shrink below 60% of the layout's font size

# ---- CSS-value sanitizers -------------------------------------------------
# Font names, colors and alignments come from untrusted decks/templates and
# are interpolated into inline `style` attributes and <style> blocks. Without
# validation a crafted typeface (e.g. `"><script>` or `x;}</style>...`) breaks
# out of the CSS context and executes in the app's origin. Everything placed
# into CSS must pass through one of these first.
_HEX6 = re.compile(r"[0-9A-Fa-f]{6}")
_FONT_STRIP = re.compile(r"[^\w \-]")
_ALIGN_OK = {"left", "center", "right", "justify", "start", "end"}


def safe_hex(value) -> str | None:
    """A validated 6-digit hex color (no leading #), or None."""
    return value if isinstance(value, str) and _HEX6.fullmatch(value) else None


def css_font(name) -> str | None:
    """A CSS-safe font-family token: keep only letters, digits, space and
    hyphen so the value cannot break out of a style attribute or <style>
    block. Empty result -> None (caller falls back to the generic family)."""
    if not isinstance(name, str):
        return None
    cleaned = _FONT_STRIP.sub("", name).strip()
    return cleaned or None


def css_align(value) -> str | None:
    """A whitelisted CSS text-align keyword, or None."""
    return value if value in _ALIGN_OK else None

# content "layout" tag -> acceptable layout purposes (ordered by preference)
LAYOUT_TYPE_ALIASES = {
    "title": ["Title Slide"],
    "section_header": ["Section Header"],
    "content": ["Title and Content", "Title and Text", "General Content"],
    "two_content": ["Two Content", "Comparison"],
    "comparison": ["Comparison", "Two Content"],
    "title_only": ["Title Only"],
    "blank": ["Blank"],
    "quote": ["Quote", "Section Header"],
    "closing": ["Closing Slide", "Title Slide"],
    "agenda": ["Agenda / Table of Contents", "Title and Content"],
    "picture": ["Picture Layout", "Picture with Caption"],
}


class LayoutNotFoundError(KeyError):
    pass


def _find_layout(manifest: dict, wanted: str) -> dict:
    layouts = manifest["layouts"]
    # exact layout-name match first
    for layout in layouts:
        if layout["name"].lower() == wanted.lower():
            return layout
    for purpose in LAYOUT_TYPE_ALIASES.get(wanted.lower(), []):
        for layout in layouts:
            if layout["purpose"] == purpose:
                return layout
    # last resort: match purpose text directly
    for layout in layouts:
        if wanted.lower() in layout["purpose"].lower():
            return layout
    raise LayoutNotFoundError(wanted)


def _asset_html(asset: dict, package_dir: Path, inline: bool,
                warnings: list[str] | None = None,
                skipped: set | None = None,
                bg_ctx: tuple[str, int, int] | None = None) -> str:
    pos, size = asset.get("position"), asset.get("size")
    if not pos or not size:
        return ""
    if asset.get("use_bg_fill") and bg_ctx:
        # painted with the slide background (masks master elements below it)
        bg_css, w_px, h_px = bg_ctx
        style = (f'position:absolute;left:{pos["x_pct"]*100:.2f}%;'
                 f'top:{pos["y_pct"]*100:.2f}%;'
                 f'width:{size["width_pct"]*100:.2f}%;'
                 f'height:{size["height_pct"]*100:.2f}%;'
                 f'z-index:{asset.get("z_order", 1)};{bg_css}'
                 f'background-size:{w_px}px {h_px}px;'
                 f'background-position:-{pos["x_pct"]*w_px:.0f}px '
                 f'-{pos["y_pct"]*h_px:.0f}px;')
        return (f'<div class="asset bg-mask" data-asset="{asset["asset_id"]}" '
                f'style="{style}"></div>')
    if asset.get("source_format") == "raster_fallback":
        # review placeholder or browser-unrenderable format (EMF/WMF):
        # omit from output rather than showing an artifact box
        if warnings is not None and skipped is not None \
                and asset["asset_id"] not in skipped:
            skipped.add(asset["asset_id"])
            warnings.append(
                f'asset "{asset["asset_id"]}" skipped: no clean web format '
                f'(flagged raster_fallback in the brandkit)')
        return ""
    style = (f'position:absolute;left:{pos["x_pct"]*100:.2f}%;'
             f'top:{pos["y_pct"]*100:.2f}%;'
             f'width:{size["width_pct"]*100:.2f}%;'
             f'height:{size["height_pct"]*100:.2f}%;'
             # flat lines have zero width/height; keep them 1px visible
             f'min-width:1px;min-height:1px;'
             f'z-index:{asset.get("z_order", 1)};')
    crop = asset.get("crop") or {}
    transforms = []
    if crop.get("rotation_deg"):
        transforms.append(f'rotate({crop["rotation_deg"]}deg)')
    if crop.get("flip_h"):
        transforms.append("scaleX(-1)")
    if crop.get("flip_v"):
        transforms.append("scaleY(-1)")
    if transforms:
        style += f'transform:{" ".join(transforms)};'

    file_path = package_dir / asset["file_path"]
    if not file_path.is_file():
        return ""
    if file_path.suffix == ".svg" and inline:
        svg = file_path.read_text(encoding="utf-8")
        # make the inlined svg fill its positioned box
        svg = svg.replace("<svg ", '<svg style="width:100%;height:100%" ', 1)
        return f'<div class="asset" data-asset="{asset["asset_id"]}" style="{style}">{svg}</div>'
    if inline:
        mime = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        b64 = base64.b64encode(file_path.read_bytes()).decode()
        src = f"data:{mime};base64,{b64}"
    else:
        src = asset["file_path"]
    fit = "cover" if asset["type"] == "background_image" else "contain"
    return (f'<img class="asset" data-asset="{asset["asset_id"]}" src="{src}" '
            f'style="{style}object-fit:{fit};" alt="">')


def _background_css(bg: dict, assets_by_id: dict) -> str:
    if bg.get("type") == "solid":
        return f'background:#{bg.get("hex", "FFFFFF")};'
    if bg.get("type") == "gradient" and bg.get("stops"):
        ordered = sorted(bg["stops"], key=lambda s: s["pos"])  # CSS needs ascending
        stops = ", ".join(f'#{s["hex"]} {s["pos"]*100:.0f}%' for s in ordered)
        angle = (bg.get("angle_deg") or 0) + 90  # OOXML 0° = left->right; CSS 90deg
        return f"background:linear-gradient({angle}deg, {stops});"
    return "background:#FFFFFF;"


def _ph_style(ph: dict, extra: str = "") -> str:
    pos, size = ph.get("position"), ph.get("size")
    if not pos or not size:
        return "position:absolute;inset:10%;"
    lvl1 = ph.get("format_levels", {}).get("1", {})
    style = (f'position:absolute;left:{pos["x_pct"]*100:.2f}%;'
             f'top:{pos["y_pct"]*100:.2f}%;'
             f'width:{size["width_pct"]*100:.2f}%;'
             f'height:{size["height_pct"]*100:.2f}%;'
             f'z-index:{ph.get("z_order", 5) + 100};'
             f'overflow:hidden;box-sizing:border-box;')
    font = css_font(lvl1.get("font"))
    if font:
        # single quotes: this lands inside a double-quoted style attribute
        style += f"font-family:'{font}', sans-serif;"
    if lvl1.get("size_pt"):
        style += f'font-size:{lvl1["size_pt"] * PX_PER_INCH / 72:.1f}px;'
    if lvl1.get("bold"):
        style += "font-weight:bold;"
    if lvl1.get("italic"):
        style += "font-style:italic;"
    color = safe_hex(lvl1.get("color"))
    if color:
        style += f'color:#{color};'
    align = css_align(lvl1.get("align"))
    if align:
        style += f'text-align:{align};'
    return style + extra


def _bullets_html(items: list, ph: dict, level: int = 1) -> str:
    levels = ph.get("format_levels", {})
    fmt = levels.get(str(level), levels.get("1", {}))
    bullet = fmt.get("bullet")
    parts = ['<ul style="list-style:none;margin:0;padding:0;">']
    for item in items:
        if isinstance(item, dict):  # {"text": ..., "children": [...]}
            text, children = item.get("text", ""), item.get("children", [])
        else:
            text, children = str(item), []
        marker = ""
        if bullet and bullet.get("kind") == "char":
            marker = f'<span class="bu">{html.escape(bullet["char"])}&nbsp;</span>'
        elif bullet and bullet.get("kind") == "number":
            marker = f'<span class="bu">•&nbsp;</span>'
        indent = 1.2 * (level - 1)
        size = ""
        if fmt.get("size_pt") and level > 1:
            size = f'font-size:{fmt["size_pt"] * PX_PER_INCH / 72:.1f}px;'
        parts.append(f'<li style="margin-left:{indent}em;{size}margin-bottom:0.35em;">'
                     f'{marker}{html.escape(text)}</li>')
        if children:
            parts.append(_bullets_html(children, ph, min(level + 1, 3)))
    parts.append("</ul>")
    return "".join(parts)


def _fill_placeholder(ph: dict, content) -> str:
    if content is None:
        return ""
    inner = (_bullets_html(content, ph) if isinstance(content, list)
             else f"<p style='margin:0'>{html.escape(str(content))}</p>")
    lvl1 = ph.get("format_levels", {}).get("1", {})
    floor_px = (lvl1.get("size_pt") or 18) * PX_PER_INCH / 72 * FONT_FLOOR_FACTOR
    return (f'<div class="ph ph-{ph["type"]}" data-fit data-floor="{floor_px:.1f}" '
            f'style="{_ph_style(ph)}">{inner}</div>')


# ------------------------------------------------------------ slide -> html

_TITLE_KEYS = ("title",)
_SUBTITLE_KEYS = ("subtitle",)
_BODY_KEYS = ("body", "bullets", "content")


def layout_furniture_html(layout: dict, assets_by_id: dict,
                          package_dir: Path, inline_assets: bool,
                          warnings: list[str],
                          bg_ctx: tuple[str, int, int] | None = None) -> str:
    """The layout's own furniture: background image, static assets/masks,
    and static texts. Shared by the rebuild and retheme preview renderers."""
    parts = []
    skipped: set = set()
    bg = layout.get("background", {})
    if bg.get("type") == "image" and bg.get("asset_id") in assets_by_id:
        parts.append(_asset_html(assets_by_id[bg["asset_id"]], package_dir,
                                 inline_assets, warnings, skipped, bg_ctx))
    for asset_id in layout.get("static_assets", []):
        asset = assets_by_id.get(asset_id)
        if asset and asset_id != bg.get("asset_id"):
            parts.append(_asset_html(asset, package_dir, inline_assets,
                                     warnings, skipped, bg_ctx))

    # layout furniture text (copyright lines, static captions)
    for st in layout.get("static_texts", []):
        pos, size, fmt = st["position"], st["size"], st.get("format", {})
        style = (f'position:absolute;left:{pos["x_pct"]*100:.2f}%;'
                 f'top:{pos["y_pct"]*100:.2f}%;'
                 f'width:{size["width_pct"]*100:.2f}%;'
                 f'min-height:{size["height_pct"]*100:.2f}%;z-index:90;')
        font = css_font(fmt.get("font"))
        if font:
            style += f"font-family:'{font}', sans-serif;"
        if fmt.get("size_pt"):
            style += f'font-size:{fmt["size_pt"] * PX_PER_INCH / 72:.1f}px;'
        if fmt.get("bold"):
            style += "font-weight:bold;"
        color = safe_hex(fmt.get("color"))
        if color:
            style += f'color:#{color};'
        align = css_align(fmt.get("align"))
        if align:
            style += f'text-align:{align};'
        body_text = "<br>".join(html.escape(p) for p in st["paragraphs"])
        parts.append(f'<div class="static-text" style="{style}">{body_text}</div>')
    return "".join(parts)


def _slide_html(slide: dict, layout: dict, assets_by_id: dict,
                package_dir: Path, inline_assets: bool,
                warnings: list[str],
                bg_ctx: tuple[str, int, int] | None = None) -> str:
    parts = [layout_furniture_html(layout, assets_by_id, package_dir,
                                   inline_assets, warnings, bg_ctx)]
    phs = layout.get("placeholders", [])

    def take(types: tuple[str, ...]):
        for ph in phs:
            if ph["type"] in types and id(ph) not in used:
                used.add(id(ph))
                return ph
        return None

    used: set[int] = set()
    for key in _TITLE_KEYS:
        if slide.get(key) is not None:
            ph = take(("title", "ctrTitle"))
            if ph is None:
                # some layouts (e.g. closing slides) carry their headline in
                # a body placeholder instead of a title placeholder
                ph = take(("body", "obj"))
            if ph:
                parts.append(_fill_placeholder(ph, slide[key]))
    for key in _SUBTITLE_KEYS:
        if slide.get(key) is not None:
            ph = take(("subTitle", "body"))
            if ph:
                parts.append(_fill_placeholder(ph, slide[key]))
    for key in _BODY_KEYS:
        if slide.get(key) is not None:
            ph = take(("body", "obj"))
            if ph:
                parts.append(_fill_placeholder(ph, slide[key]))
            else:
                warnings.append(
                    f'slide "{slide.get("title", "?")}": no free body '
                    f'placeholder on layout "{layout["name"]}" for "{key}"')
    # two-content style: left/right columns
    for side in ("left", "right"):
        col = slide.get(side)
        if col is not None:
            ph = take(("body", "obj"))
            if ph:
                parts.append(_fill_placeholder(ph, col))
            else:
                warnings.append(
                    f'slide "{slide.get("title", "?")}": layout '
                    f'"{layout["name"]}" has no placeholder for "{side}" column')

    parts.append(_rich_content_html(slide))
    return "".join(parts)


def _box_style(g: dict, z: int = 150) -> str:
    return (f'position:absolute;left:{g["x_pct"]*100:.2f}%;'
            f'top:{g["y_pct"]*100:.2f}%;width:{g["w_pct"]*100:.2f}%;'
            f'height:{g["h_pct"]*100:.2f}%;z-index:{z};')


def _rich_content_html(slide: dict) -> str:
    """Pictures (as-is), tables (text grid) and chart markers carried over
    from a content deck. The PPTX export retains these natively."""
    parts = []
    for img in slide.get("images", []):
        parts.append(
            f'<img class="content-img" src="data:{img["mime"]};base64,'
            f'{img["data_b64"]}" style="{_box_style(img)}'
            f'object-fit:contain;" alt="">')
    for tbl in slide.get("tables", []):
        rows = tbl.get("rows", [])
        if not rows:
            continue
        head = "".join(f"<th>{html.escape(c)}</th>" for c in rows[0])
        body = "".join(
            "<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in row) + "</tr>"
            for row in rows[1:])
        parts.append(
            f'<div class="content-table" style="{_box_style(tbl)}overflow:auto;">'
            f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody>'
            f'</table></div>')
    for ch in slide.get("charts", []):
        label = html.escape(ch.get("title") or "Chart")
        parts.append(
            f'<div class="content-chart" style="{_box_style(ch)}">'
            f'<span>{label}<br><small>chart — fully retained in the '
            f'PPTX export</small></span></div>')
    return "".join(parts)


_FIT_SCRIPT = """
// Overflow fallback (spec §4.2): shrink font-size down to a defined floor;
// if still overflowing, flag the element instead of letting text spill.
document.querySelectorAll('[data-fit]').forEach(function (el) {
  var floor = parseFloat(el.dataset.floor) || 10;
  var size = parseFloat(getComputedStyle(el).fontSize);
  var guard = 40;
  while (el.scrollHeight > el.clientHeight + 1 && size > floor && guard-- > 0) {
    size -= 1;
    el.style.fontSize = size + 'px';
    el.querySelectorAll('li,p').forEach(function (c) { c.style.fontSize = ''; });
  }
  if (el.scrollHeight > el.clientHeight + 1) {
    el.classList.add('overflow-flagged');
    el.setAttribute('data-overflow', 'true');
  }
});
// Scale the preview to the viewport width (applied after overflow
// measurement so it doesn't affect the fit logic above).
(function () {
  var slide = document.querySelector('.slide');
  if (!slide) return;
  function fit() {
    var scale = Math.min(1, (window.innerWidth - 24) / slide.offsetWidth);
    document.body.style.zoom = scale;
  }
  fit();
  window.addEventListener('resize', fit);
})();
"""


def generate_html(package_dir: str | Path, content: dict,
                  inline_assets: bool = True) -> tuple[str, list[str]]:
    """Returns (html_text, warnings)."""
    package_dir = Path(package_dir)
    manifest = json.loads((package_dir / "template.json").read_text(encoding="utf-8"))
    geo = manifest["slide_geometry"]
    w_px = round(geo["width_in"] * PX_PER_INCH)
    h_px = round(geo["height_in"] * PX_PER_INCH)
    assets_by_id = {a["asset_id"]: a for a in manifest["assets"]}
    fonts = manifest.get("fonts", {})

    warnings: list[str] = []
    vw = version_warning(manifest)
    if vw:
        warnings.append(vw)
    slides_html = []
    for i, slide in enumerate(content.get("slides", [])):
        wanted = slide.get("layout", "content")
        try:
            layout = _find_layout(manifest, wanted)
        except LayoutNotFoundError:
            # spec §4.4: flag unsupported rather than improvising
            warnings.append(f'slide {i + 1}: no layout matches "{wanted}" — flagged')
            slides_html.append(
                f'<section class="slide unsupported" style="background:#FDECEC">'
                f'<div style="position:absolute;inset:10%;font-family:sans-serif;'
                f'color:#B3261E"><h2>Unsupported layout: {html.escape(wanted)}</h2>'
                f'<p>No matching layout in the template package. '
                f'Available: {html.escape(", ".join(l["name"] for l in manifest["layouts"][:12]))}…'
                f'</p></div></section>')
            continue
        bg_css = _background_css(layout.get("background", {}), assets_by_id)
        body = _slide_html(slide, layout, assets_by_id, package_dir,
                           inline_assets, warnings, (bg_css, w_px, h_px))
        slides_html.append(
            f'<section class="slide" data-layout="{html.escape(layout["name"])}" '
            f'style="{bg_css}">{body}</section>')

    title = content.get("title", manifest.get("template_name", "Deck"))
    return doc_wrapper(manifest, slides_html, title), \
        list(dict.fromkeys(warnings))


def version_warning(manifest: dict) -> str | None:
    from .. import __version__
    pkg_version = manifest.get("extractor_version", "pre-0.2.0")
    if pkg_version != __version__:
        return (f"BRANDKIT OUTDATED: this package was extracted with tool "
                f"version {pkg_version}, but the current version is "
                f"{__version__}. The HTML output may not match the PPTX — "
                f"re-extract the template to refresh the brandkit.")
    return None


def doc_wrapper(manifest: dict, slides_html: list[str], title: str) -> str:
    """Full HTML document around rendered slide sections. Shared by the
    rebuild renderer (this module) and the retheme preview renderer."""
    geo = manifest["slide_geometry"]
    w_px = round(geo["width_in"] * PX_PER_INCH)
    h_px = round(geo["height_in"] * PX_PER_INCH)
    fonts = manifest.get("fonts", {})
    title = html.escape(title)
    # these land in a <style> block; an unsanitized font could carry
    # `</style><script>…`, so validate before interpolating
    heading_font = css_font(fonts.get("heading")) or "sans-serif"
    body_font = css_font(fonts.get("body")) or "sans-serif"
    primary = safe_hex(next((c["hex"] for c in manifest.get("colors", [])
                             if c.get("role") == "primary"), None)) or "333333"
    css = f"""
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#333; font-family:"{body_font}", sans-serif; }}
.slide {{
  position:relative; width:{w_px}px; height:{h_px}px;
  margin:16px auto; overflow:hidden; box-shadow:0 2px 12px rgba(0,0,0,.4);
}}
.ph-title, .ph-ctrTitle {{ font-family:"{heading_font}", sans-serif; }}
.ph p, .ph li {{ line-height:1.25; }}
.bu {{ display:inline-block; min-width:1em; }}
.overflow-flagged {{ outline:3px dashed #B3261E; }}
.content-table table {{ border-collapse:collapse; width:100%; font-size:14px;
  font-family:"{body_font}", sans-serif; background:#fff; }}
.content-table th {{ background:#{primary}; color:#fff; padding:4px 10px;
  text-align:left; }}
.content-table td {{ border-bottom:1px solid #ddd; padding:4px 10px; }}
.content-chart {{ border:2px dashed #{primary}; color:#{primary};
  display:flex; align-items:center; justify-content:center;
  text-align:center; font-family:"{heading_font}", sans-serif;
  background:rgba(255,255,255,.5); }}
@media print {{ .slide {{ margin:0; page-break-after:always; box-shadow:none; }} }}
"""
    return (f"<!DOCTYPE html>\n<html><head><meta charset='utf-8'>"
            f"<title>{title}</title><style>{css}</style></head>\n<body>\n"
            + "\n".join(slides_html)
            + f"\n<script>{_FIT_SCRIPT}</script>\n</body></html>\n")


def generate_file(package_dir: str | Path, content_path: str | Path,
                  out_path: str | Path, inline_assets: bool = True) -> list[str]:
    content = json.loads(Path(content_path).read_text(encoding="utf-8"))
    doc, warnings = generate_html(package_dir, content, inline_assets)
    Path(out_path).write_text(doc, encoding="utf-8")
    return warnings
