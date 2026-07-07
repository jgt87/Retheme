"""Generate a real .pptx from a template package + content JSON.

Preferred path: the package embeds the original template
(manifest["source_template"]); slides are then built on the template's own
layouts, so backgrounds, decorations, fonts and colors are native and the
result is fully editable in PowerPoint.

Fallback path (older package without the source): an approximate deck is
built from the manifest alone — solid/gradient backgrounds, raster assets,
positioned text boxes. Vector (SVG) decorations are skipped with a warning.
"""

from __future__ import annotations

import base64
import io
import json
import shutil
import tempfile
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Pt

from ..ooxml import NS
from .generator import LAYOUT_TYPE_ALIASES, LayoutNotFoundError, _find_layout

EMU_PER_INCH = 914400


# --------------------------------------------------------------- helpers

def _ph_type_of(shape) -> str | None:
    ph = shape._element.find(".//p:nvSpPr/p:nvPr/p:ph", NS)
    if ph is None:
        ph = shape._element.find(".//p:nvPicPr/p:nvPr/p:ph", NS)
    return ph.get("type", "obj") if ph is not None else None


def _flatten(items, level=0):
    """Content bullets (strings / {text, children}) -> [(level, text)]."""
    out = []
    for item in items or []:
        if isinstance(item, dict):
            out.append((level, item.get("text", "")))
            out.extend(_flatten(item.get("children", []), level + 1))
        else:
            out.append((level, str(item)))
    return out


def _fill_text_frame(tf, content):
    if isinstance(content, list):
        rows = _flatten(content)
    else:
        rows = [(0, str(content))]
    tf.clear()
    for i, (level, text) in enumerate(rows):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.text = text
        para.level = min(level, 8)


def _delete_all_slides(prs):
    xml_slides = prs.slides._sldIdLst
    r_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    for sld in list(xml_slides):
        prs.part.drop_rel(sld.get(r_ns))
        xml_slides.remove(sld)


def _add_content_images(slide, images, slide_w, slide_h, warnings, slide_no):
    """Place the content deck's own pictures onto the rebuilt slide.

    content_extract keeps them as percent-positioned, base64-encoded blobs;
    the HTML preview renders them, so the PPTX export must too or the picture
    silently vanishes on download.
    """
    for img in images or []:
        data = img.get("data_b64")
        if not data:
            continue
        try:
            slide.shapes.add_picture(
                io.BytesIO(base64.b64decode(data)),
                Emu(round(img.get("x_pct", 0) * slide_w)),
                Emu(round(img.get("y_pct", 0) * slide_h)),
                Emu(round(img.get("w_pct", 0) * slide_w)),
                Emu(round(img.get("h_pct", 0) * slide_h)))
        except Exception:
            warnings.append(
                f"slide {slide_no}: a content image could not be placed in "
                f"the PPTX export and was skipped")


# --------------------------------------------- path 1: native template

def _generate_from_source(source_path: Path, manifest: dict, content: dict,
                          out_path: Path) -> list[str]:
    from ..extractor.extract import _as_presentation

    warnings: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="pptx-gen-"))
    try:
        prs = Presentation(str(_as_presentation(source_path, tmp)))
        _delete_all_slides(prs)

        layouts_by_name = {}
        for master in prs.slide_masters:
            for layout in master.slide_layouts:
                layouts_by_name.setdefault(layout.name, layout)
        fallback_layout = next(iter(layouts_by_name.values()))

        for i, slide_spec in enumerate(content.get("slides", []), start=1):
            wanted = slide_spec.get("layout", "content")
            try:
                layout_def = _find_layout(manifest, wanted)
                layout = layouts_by_name.get(layout_def["name"])
            except LayoutNotFoundError:
                layout = None
            if layout is None:
                warnings.append(f'slide {i}: no layout matches "{wanted}" — '
                                f'placed on "{fallback_layout.name}" and flagged')
                slide = prs.slides.add_slide(fallback_layout)
                box = slide.shapes.add_textbox(Emu(EMU_PER_INCH // 2),
                                               Emu(EMU_PER_INCH // 2),
                                               Emu(EMU_PER_INCH * 8),
                                               Emu(EMU_PER_INCH))
                box.text_frame.text = f'[unsupported layout: {wanted}]'
                box.text_frame.paragraphs[0].runs[0].font.color.rgb = \
                    RGBColor(0xB3, 0x26, 0x1E)
                _add_content_images(slide, slide_spec.get("images"),
                                    prs.slide_width, prs.slide_height,
                                    warnings, i)
                continue

            slide = prs.slides.add_slide(layout)
            used = set()

            def take(types):
                for ph in slide.placeholders:
                    if _ph_type_of(ph) in types and ph.shape_id not in used:
                        used.add(ph.shape_id)
                        return ph
                return None

            if slide_spec.get("title") is not None:
                ph = take(("title", "ctrTitle"))
                if ph is None:
                    # closing-style layouts keep the headline in a body ph
                    ph = take(("body", "obj"))
                if ph is not None:
                    ph.text_frame.text = str(slide_spec["title"])
            if slide_spec.get("subtitle") is not None:
                ph = take(("subTitle", "body"))
                if ph is not None:
                    ph.text_frame.text = str(slide_spec["subtitle"])
            for key in ("body", "bullets", "content"):
                if slide_spec.get(key) is not None:
                    ph = take(("body", "obj"))
                    if ph is not None:
                        _fill_text_frame(ph.text_frame, slide_spec[key])
                    else:
                        warnings.append(
                            f'slide {i}: no free body placeholder on layout '
                            f'"{layout.name}" for "{key}"')
            for side in ("left", "right"):
                if slide_spec.get(side) is not None:
                    ph = take(("body", "obj"))
                    if ph is not None:
                        _fill_text_frame(ph.text_frame, slide_spec[side])
                    else:
                        warnings.append(
                            f'slide {i}: layout "{layout.name}" has no '
                            f'placeholder for "{side}" column')

            _add_content_images(slide, slide_spec.get("images"),
                                prs.slide_width, prs.slide_height, warnings, i)

        prs.save(str(out_path))
        return warnings
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------- path 2: manifest fallback

def _generate_from_manifest(package_dir: Path, manifest: dict, content: dict,
                            out_path: Path) -> list[str]:
    warnings = ["package has no embedded source template: output is an "
                "approximation (vector decorations are skipped)"]
    prs = Presentation()
    geo = manifest["slide_geometry"]
    prs.slide_width = Emu(round(geo["width_in"] * EMU_PER_INCH))
    prs.slide_height = Emu(round(geo["height_in"] * EMU_PER_INCH))
    blank = prs.slide_layouts[6]
    assets_by_id = {a["asset_id"]: a for a in manifest["assets"]}
    align_map = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER,
                 "right": PP_ALIGN.RIGHT, "justify": PP_ALIGN.JUSTIFY}

    for i, slide_spec in enumerate(content.get("slides", []), start=1):
        slide = prs.slides.add_slide(blank)
        try:
            layout_def = _find_layout(manifest, slide_spec.get("layout", "content"))
        except LayoutNotFoundError:
            warnings.append(f'slide {i}: no layout matches '
                            f'"{slide_spec.get("layout")}" — blank slide used')
            _add_content_images(slide, slide_spec.get("images"),
                                prs.slide_width, prs.slide_height, warnings, i)
            continue

        bg = layout_def.get("background", {})
        fill = slide.background.fill
        if bg.get("type") == "solid":
            fill.solid()
            fill.fore_color.rgb = RGBColor.from_string(bg.get("hex", "FFFFFF"))
        elif bg.get("type") == "gradient" and bg.get("stops"):
            fill.solid()  # approximate with the dominant (lowest-pos) stop
            first = min(bg["stops"], key=lambda s: s["pos"])
            fill.fore_color.rgb = RGBColor.from_string(first["hex"])
        elif bg.get("type") == "image" and bg.get("asset_id"):
            bg_asset = assets_by_id.get(bg["asset_id"])
            bg_file = package_dir / bg_asset["file_path"] if bg_asset else None
            if bg_file and bg_file.is_file() and bg_file.suffix.lower() != ".svg":
                slide.shapes.add_picture(str(bg_file), 0, 0,
                                         prs.slide_width, prs.slide_height)
            else:
                warnings.append(f"slide {i}: background image unavailable")

        for asset_id in layout_def.get("static_assets", []):
            asset = assets_by_id.get(asset_id)
            if not asset or not asset.get("position") or not asset.get("size") \
                    or not asset.get("file_path"):
                continue
            path = package_dir / asset["file_path"]
            if path.suffix.lower() == ".svg" or not path.is_file():
                continue  # no rasterizer available for vector assets
            pos, size = asset["position"], asset["size"]
            try:
                slide.shapes.add_picture(
                    str(path),
                    Emu(round(pos["x_in"] * EMU_PER_INCH)),
                    Emu(round(pos["y_in"] * EMU_PER_INCH)),
                    Emu(round(size["width_in"] * EMU_PER_INCH)),
                    Emu(round(size["height_in"] * EMU_PER_INCH)))
            except Exception:
                warnings.append(f'slide {i}: could not place asset {asset_id}')

        for st in layout_def.get("static_texts", []):
            pos, size = st["position"], st["size"]
            box = slide.shapes.add_textbox(
                Emu(round(pos["x_in"] * EMU_PER_INCH)),
                Emu(round(pos["y_in"] * EMU_PER_INCH)),
                Emu(round(size["width_in"] * EMU_PER_INCH)),
                Emu(round(max(size["height_in"], 0.15) * EMU_PER_INCH)))
            _fill_text_frame(box.text_frame, st["paragraphs"])
            fmt = st.get("format", {})
            for para in box.text_frame.paragraphs:
                if fmt.get("font"):
                    para.font.name = fmt["font"]
                if fmt.get("size_pt"):
                    para.font.size = Pt(fmt["size_pt"])
                if fmt.get("color"):
                    para.font.color.rgb = RGBColor.from_string(fmt["color"])

        used = set()

        def put_text(ph_types, text_content):
            for ph in layout_def.get("placeholders", []):
                if ph["type"] not in ph_types or id(ph) in used:
                    continue
                used.add(id(ph))
                pos, size = ph.get("position"), ph.get("size")
                if not pos or not size:
                    return
                box = slide.shapes.add_textbox(
                    Emu(round(pos["x_in"] * EMU_PER_INCH)),
                    Emu(round(pos["y_in"] * EMU_PER_INCH)),
                    Emu(round(size["width_in"] * EMU_PER_INCH)),
                    Emu(round(size["height_in"] * EMU_PER_INCH)))
                tf = box.text_frame
                tf.word_wrap = True
                _fill_text_frame(tf, text_content)
                fmt = ph.get("format_levels", {}).get("1", {})
                for para in tf.paragraphs:
                    if fmt.get("align") in align_map:
                        para.alignment = align_map[fmt["align"]]
                    font = para.font
                    if fmt.get("font"):
                        font.name = fmt["font"]
                    if fmt.get("size_pt"):
                        font.size = Pt(fmt["size_pt"])
                    if fmt.get("bold"):
                        font.bold = True
                    if fmt.get("color"):
                        font.color.rgb = RGBColor.from_string(fmt["color"])
                return

        if slide_spec.get("title") is not None:
            put_text(("title", "ctrTitle"), slide_spec["title"])
        if slide_spec.get("subtitle") is not None:
            put_text(("subTitle", "body"), slide_spec["subtitle"])
        for key in ("body", "bullets", "content"):
            if slide_spec.get(key) is not None:
                put_text(("body", "obj"), slide_spec[key])
        for side in ("left", "right"):
            if slide_spec.get(side) is not None:
                put_text(("body", "obj"), slide_spec[side])

        _add_content_images(slide, slide_spec.get("images"),
                            prs.slide_width, prs.slide_height, warnings, i)

    prs.save(str(out_path))
    return warnings


# --------------------------------------------------------------- public

def generate_pptx(package_dir: str | Path, content: dict,
                  out_path: str | Path) -> list[str]:
    package_dir = Path(package_dir)
    out_path = Path(out_path)
    manifest = json.loads(
        (package_dir / "template.json").read_text(encoding="utf-8"))
    source_rel = manifest.get("source_template")
    source_path = package_dir / source_rel if source_rel else None
    if source_path and source_path.is_file():
        return _generate_from_source(source_path, manifest, content, out_path)
    return _generate_from_manifest(package_dir, manifest, content, out_path)


def generate_pptx_file(package_dir: str | Path, content_path: str | Path,
                       out_path: str | Path) -> list[str]:
    content = json.loads(Path(content_path).read_text(encoding="utf-8"))
    return generate_pptx(package_dir, content, out_path)
