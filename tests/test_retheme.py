"""Retheme regression tests: applying a brandkit to a content deck must
RETAIN pictures (byte-identical), tables, charts and other objects, and
recolor chart colors that match the source theme to the brandkit theme."""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Emu, Inches

from pptx_template_tool.application.content_extract import extract_content
from pptx_template_tool.application.generator import generate_html
from pptx_template_tool.application.retheme import (_recolor_srgb,
                                                    retheme_pptx)
from pptx_template_tool.extractor.extract import extract_template

from .test_extraction_nuances import build_template, _png_bytes


def _make_content_deck(tmp_path: Path) -> tuple[Path, bytes]:
    """A deck with title, bullets, a picture, a table and a chart."""
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])  # title only
    slide.shapes.title.text = "Rich content"

    img_bytes = _png_bytes((200, 30, 90))
    slide.shapes.add_picture(io.BytesIO(img_bytes), Inches(0.5), Inches(2),
                             Inches(2), Inches(1.5))

    table = slide.shapes.add_table(2, 2, Inches(3), Inches(2),
                                   Inches(3), Inches(1)).table
    table.cell(0, 0).text = "Region"
    table.cell(0, 1).text = "Sales"
    table.cell(1, 0).text = "EMEA"
    table.cell(1, 1).text = "42"

    chart_data = CategoryChartData()
    chart_data.categories = ["A", "B"]
    chart_data.add_series("S1", (1.0, 2.0))
    slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED,
                           Inches(6.5), Inches(2), Inches(3), Inches(2.5),
                           chart_data)

    deck = tmp_path / "content-deck.pptx"
    prs.save(str(deck))
    return deck, img_bytes


def _brandkit(tmp_path: Path) -> Path:
    pptx = build_template(tmp_path, as_potx=True)
    pkg = tmp_path / "brand-pkg"
    extract_template(pptx, pkg)
    return pkg


def test_retheme_retains_everything(tmp_path):
    deck, img_bytes = _make_content_deck(tmp_path)
    pkg = _brandkit(tmp_path)
    out = tmp_path / "branded.pptx"
    retheme_pptx(pkg, deck, out)

    prs = Presentation(str(out))
    assert len(prs.slides) == 1
    slide = prs.slides[0]

    # picture kept byte-for-byte
    pics = [sh for sh in slide.shapes if sh.shape_type == 13]  # PICTURE
    assert pics, "picture lost during retheme"
    assert hashlib.sha1(pics[0].image.blob).hexdigest() == \
        hashlib.sha1(img_bytes).hexdigest()

    # table retained with its text
    tables = [sh for sh in slide.shapes
              if getattr(sh, "has_table", False) and sh.has_table]
    assert tables and tables[0].table.cell(1, 0).text == "EMEA"

    # chart retained as a real chart part
    charts = [sh for sh in slide.shapes
              if getattr(sh, "has_chart", False) and sh.has_chart]
    assert charts and len(charts[0].chart.plots[0].series[0].values) == 2

    # title text retained
    texts = [sh.text_frame.text for sh in slide.shapes if sh.has_text_frame]
    assert any("Rich content" in t for t in texts)

    # slides sit on the brandkit's layouts (its own theme applies)
    assert slide.slide_layout.part.package is prs.part.package


def test_partcloner_assigns_unique_part_names(tmp_path):
    """Cloning many related parts must yield unique part names and a valid
    package (guards the O(n) part-name allocator against collisions)."""
    import zipfile as zf

    prs = Presentation()
    for n in range(6):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        # distinct image bytes per slide so none dedupe away
        slide.shapes.add_picture(
            io.BytesIO(_png_bytes((n * 30 % 255, n * 17 % 255, 50))),
            Inches(1), Inches(1), Inches(2), Inches(1.5))
    deck = tmp_path / "many-images.pptx"
    prs.save(str(deck))

    pkg = _brandkit(tmp_path)
    out = tmp_path / "branded.pptx"
    retheme_pptx(pkg, deck, out)

    with zf.ZipFile(out) as z:
        names = z.namelist()
        assert len(names) == len(set(names)), "duplicate part names emitted"
        assert z.testzip() is None
        assert len([n for n in names if "/media/" in n]) >= 6


def test_retheme_output_is_valid_package(tmp_path):
    deck, _ = _make_content_deck(tmp_path)
    pkg = _brandkit(tmp_path)
    out = tmp_path / "branded.pptx"
    retheme_pptx(pkg, deck, out)
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert any("charts/chart" in n for n in names)
        assert any("media/" in n for n in names)
        assert z.testzip() is None


def test_chart_recolor_maps_theme_colors():
    blob = (b'<a:solidFill xmlns:a="http://schemas.openxmlformats.org/'
            b'drawingml/2006/main"><a:srgbClr val="4F81BD"/></a:solidFill>')
    out = _recolor_srgb(blob, {"4F81BD": "10069F"})
    assert b'10069F' in out and b'4F81BD' not in out
    # colors not in the source theme stay untouched
    out2 = _recolor_srgb(blob, {"FF0000": "10069F"})
    assert out2 is blob


def test_html_preview_shows_rich_content(tmp_path):
    deck, _ = _make_content_deck(tmp_path)
    pkg = _brandkit(tmp_path)
    content, _ = extract_content(deck, pkg)
    slide = content["slides"][0]
    assert slide.get("images") and slide["images"][0]["data_b64"]
    assert slide.get("tables") and slide["tables"][0]["rows"][1][0] == "EMEA"
    assert slide.get("charts")

    html, _ = generate_html(pkg, content)
    assert "data:image/png;base64" in html
    assert "EMEA" in html
    assert "content-chart" in html


def test_content_images_survive_manifest_pptx_export(tmp_path):
    """A content picture visible in the HTML preview must also land in the
    rebuilt PPTX on the manifest fallback path (no embedded source template),
    not silently vanish on download."""
    import json
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    from pptx_template_tool.application.pptx_generator import generate_pptx

    deck, _ = _make_content_deck(tmp_path)
    pkg = _brandkit(tmp_path)
    content, _ = extract_content(deck, pkg)
    assert content["slides"][0].get("images")  # extraction kept the picture

    # force the manifest rebuild path by dropping the embedded source template
    manifest = json.loads((pkg / "template.json").read_text("utf-8"))
    manifest.pop("source_template", None)
    (pkg / "template.json").write_text(json.dumps(manifest), encoding="utf-8")

    out = tmp_path / "branded.pptx"
    generate_pptx(pkg, content, out)
    prs = Presentation(str(out))
    pics = sum(1 for slide in prs.slides for sh in slide.shapes
               if sh.shape_type == MSO_SHAPE_TYPE.PICTURE)
    assert pics >= 1


def test_slide_to_slide_correspondence(tmp_path):
    """Content of source slide N must land on output slide N — never merge
    into, or spill over to, a neighboring slide."""
    prs = Presentation()
    markers = []
    prs.slides.add_slide(prs.slide_layouts[0]).shapes.title.text = "Deck Title"
    markers.append("Deck Title")
    for n in range(2, 6):  # slides 2..5, each with unique text + a picture
        slide = prs.slides.add_slide(prs.slide_layouts[5])
        slide.shapes.title.text = f"UNIQUE-SLIDE-{n}"
        slide.shapes.add_picture(
            io.BytesIO(_png_bytes((n * 40 % 255, 10, 10))),
            Inches(1), Inches(2), Inches(2), Inches(1))
        markers.append(f"UNIQUE-SLIDE-{n}")
    deck = tmp_path / "five.pptx"
    prs.save(str(deck))

    pkg = _brandkit(tmp_path)
    out = tmp_path / "branded5.pptx"
    retheme_pptx(pkg, deck, out)

    branded = Presentation(str(out))
    assert len(branded.slides) == 5  # nothing added, dropped, or merged
    for i, slide in enumerate(branded.slides):
        texts = " ".join(sh.text_frame.text for sh in slide.shapes
                         if sh.has_text_frame)
        assert markers[i] in texts, f"slide {i+1} lost its own content"
        for j, other in enumerate(markers):
            if j != i:
                assert other not in texts, \
                    f"slide {i+1} contains content from slide {j+1}"
        if i >= 1:  # picture stays on its own slide
            assert any(sh.shape_type == 13 for sh in slide.shapes)

    # the HTML preview must keep the same 1:1 slide order
    content, _ = extract_content(deck, pkg)
    assert len(content["slides"]) == 5
    html, _ = generate_html(pkg, content)
    positions = [html.index(m) for m in markers]
    assert positions == sorted(positions), "HTML slide order broken"


def _brandkit_with_distinct_theme(tmp_path: Path) -> Path:
    """Brand template whose theme differs from Office defaults: accent1 becomes
    10069F (source default is 4F81BD) and fonts become Verdana."""
    import zipfile as zf
    pptx = build_template(tmp_path, as_potx=True)
    patched = tmp_path / "brand-theme.potx"
    with zf.ZipFile(pptx) as src, zf.ZipFile(patched, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name.startswith("ppt/theme/theme"):
                data = data.replace(b'val="4F81BD"', b'val="10069F"')
                data = data.replace(b'typeface="Calibri"',
                                    b'typeface="Verdana"')
            dst.writestr(name, data)
    pkg = tmp_path / "brand-theme-pkg"
    extract_template(patched, pkg)
    return pkg


def test_retheme_restyles_hardcoded_colors_fonts_and_title_sizes(tmp_path):
    from pptx.dml.color import RGBColor
    from pptx.util import Pt

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    title_run = slide.shapes.title.text_frame.paragraphs[0]
    slide.shapes.title.text = "Styled Title"
    run = slide.shapes.title.text_frame.paragraphs[0].runs[0]
    run.font.size = Pt(13)                      # hard-coded size on a title
    box = slide.shapes.add_textbox(Inches(1), Inches(3), Inches(4), Inches(1))
    r = box.text_frame.paragraphs[0].add_run()
    r.text = "hardcoded style"
    r.font.name = "Calibri"                     # source theme minor font
    r.font.color.rgb = RGBColor.from_string("4F81BD")  # source accent1
    orig_left, orig_top = box.left, box.top
    deck = tmp_path / "styled.pptx"
    prs.save(str(deck))

    pkg = _brandkit_with_distinct_theme(tmp_path)
    out = tmp_path / "restyled.pptx"
    retheme_pptx(pkg, deck, out)

    branded = Presentation(str(out))
    slide = branded.slides[0]
    boxes = [sh for sh in slide.shapes if sh.has_text_frame
             and "hardcoded style" in sh.text_frame.text]
    assert boxes, "text box lost"
    run = boxes[0].text_frame.paragraphs[0].runs[0]
    assert str(run.font.color.rgb) == "10069F"   # brand accent applied
    assert run.font.name == "Verdana"            # brand minor font applied
    assert boxes[0].left == orig_left and boxes[0].top == orig_top  # position kept

    titles = [sh for sh in slide.shapes if sh.has_text_frame
              and "Styled Title" in sh.text_frame.text]
    assert titles
    t_run = titles[0].text_frame.paragraphs[0].runs[0]
    assert t_run.font.size is None  # explicit size stripped -> brand layout size


def _two_slide_colored_deck(tmp_path: Path) -> Path:
    """Two slides, each with a run hard-coded to the source theme's accent1
    (4F81BD) — which the default retheme rebrands to the brand accent1."""
    from pptx.dml.color import RGBColor
    prs = Presentation()
    for n in ("one", "two"):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
        r = box.text_frame.paragraphs[0].add_run()
        r.text = f"slide {n}"
        r.font.color.rgb = RGBColor.from_string("4F81BD")
    deck = tmp_path / "two.pptx"
    prs.save(str(deck))
    return deck


def _run_color(slide) -> str | None:
    for sh in slide.shapes:
        if sh.has_text_frame and sh.text_frame.paragraphs[0].runs:
            return str(sh.text_frame.paragraphs[0].runs[0].font.color.rgb)
    return None


def test_protected_slide_full_retains_original(tmp_path):
    """A slide protected with mode 'full' ignores the choices entirely: its
    hard-coded colors are not rebranded while unprotected slides are."""
    deck = _two_slide_colored_deck(tmp_path)
    pkg = _brandkit_with_distinct_theme(tmp_path)
    out = tmp_path / "out.pptx"
    retheme_pptx(pkg, deck, out,
                 choices={"__protect__": "1", "__protect_mode__": "full"})
    branded = Presentation(str(out))
    assert _run_color(branded.slides[0]) == "4F81BD"   # protected: unchanged
    assert _run_color(branded.slides[1]) == "10069F"   # rebranded


def test_protected_slide_partial_skips_unselected(tmp_path):
    """Mode 'partial' applies only the ticked adjustment categories; colors
    left unticked are not rebranded on the protected slide."""
    deck = _two_slide_colored_deck(tmp_path)
    pkg = _brandkit_with_distinct_theme(tmp_path)
    out = tmp_path / "out.pptx"
    retheme_pptx(pkg, deck, out,
                 choices={"__protect__": "1", "__protect_mode__": "partial",
                          "__protect_apply__": "font,title,heading,resize"})
    branded = Presentation(str(out))
    assert _run_color(branded.slides[0]) == "4F81BD"   # color skipped
    assert _run_color(branded.slides[1]) == "10069F"   # fully rebranded


def test_full_retain_bakes_theme_colors_to_source(tmp_path):
    """Freezing converts theme-linked (schemeClr) colors to the SOURCE hex, so
    the brand theme the slide now lands under cannot shift its appearance."""
    from pptx.enum.dml import MSO_THEME_COLOR
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    sh = slide.shapes.add_shape(1, Inches(1), Inches(1), Inches(2), Inches(1))
    sh.fill.solid()
    sh.fill.fore_color.theme_color = MSO_THEME_COLOR.ACCENT_1  # schemeClr accent1
    deck = tmp_path / "themed.pptx"
    prs.save(str(deck))

    pkg = _brandkit_with_distinct_theme(tmp_path)  # brand accent1 = 10069F
    out = tmp_path / "out.pptx"
    retheme_pptx(pkg, deck, out,
                 choices={"__protect__": "1", "__protect_mode__": "full"})
    shape = Presentation(str(out)).slides[0].shapes[0]
    assert str(shape.fill.fore_color.rgb) == "4F81BD"  # source accent1, baked in


def test_preview_renders_from_rethemed_deck(tmp_path):
    """The HTML preview must be rendered FROM the rethemed PPTX: content at
    its true positions, pictures/tables inline, layout furniture behind."""
    from pptx_template_tool.application.preview_render import render_deck_html

    deck, _ = _make_content_deck(tmp_path)
    pkg = _brandkit(tmp_path)
    branded = tmp_path / "branded.pptx"
    retheme_pptx(pkg, deck, branded)
    html, _ = render_deck_html(pkg, branded, "t")

    assert html.count('<section class="slide"') == 1
    assert "data:image/png;base64" in html          # picture inline
    assert "EMEA" in html and "Rich content" in html  # table + title text
    assert "content-chart" in html                   # chart marker
    # picture sits at its true source position (0.5in of 10in = 5%)
    import re
    m = re.search(r'<img [^>]*style="position:absolute;left:([\d.]+)%', html)
    assert m and abs(float(m.group(1)) - 5.0) < 0.5


def test_palette_harmonization(tmp_path):
    """Hard-coded off-theme colors: the dominant family is remapped to the
    brand primary (lightness preserved); minority status colors and
    neutrals are kept."""
    from pptx.dml.color import RGBColor

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    colors = ["1E2761", "1E2761", "1E2761", "D7DEEE", "D7DEEE",  # blues (dominant)
              "DC2626",                                          # red (semantic)
              "FFFFFF"]                                          # neutral
    for i, hexval in enumerate(colors):
        box = slide.shapes.add_shape(1, Inches(0.5 + i), Inches(1),
                                     Inches(0.8), Inches(0.8))
        box.fill.solid()
        box.fill.fore_color.rgb = RGBColor.from_string(hexval)

    deck = tmp_path / "webpalette.pptx"
    prs.save(str(deck))
    pkg = _brandkit_with_distinct_theme(tmp_path)  # primary 10069F
    out = tmp_path / "harmonized.pptx"
    warnings = retheme_pptx(pkg, deck, out)

    import zipfile as zf
    slide_xml = zf.ZipFile(out).read("ppt/slides/slide1.xml").decode()
    assert "1E2761" not in slide_xml, "dominant dark blue not remapped"
    assert "D7DEEE" not in slide_xml, "dominant light tint not remapped"
    assert "DC2626" in slide_xml, "semantic red must be kept"
    assert "FFFFFF" in slide_xml, "neutral white must be kept"
    assert any("recolored to the brand primary" in w for w in warnings)

    # remapped colors carry the brand hue with original lightness ordering
    from pptx_template_tool.application.retheme import _hex_hls
    import re
    new_hexes = set(re.findall(r'srgbClr val="([0-9A-F]{6})"', slide_xml))
    new_blues = [h for h in new_hexes
                 if h not in {"DC2626", "FFFFFF"} and _hex_hls(h)[2] > 0.3]
    brand_h = _hex_hls("10069F")[0]
    for h in new_blues:
        hue = _hex_hls(h)[0]
        d = min(abs(hue - brand_h), 1 - abs(hue - brand_h))
        assert d < 0.05, f"{h} not in brand hue family"


def test_conflict_analysis_and_choices(tmp_path):
    """Uncertain brandkit-vs-deck decisions are surfaced for confirmation,
    and the user's choices are honored by the retheme."""
    from pptx.dml.color import RGBColor
    from pptx_template_tool.application.conflicts import analyze_conflicts

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    for i, hexval in enumerate(["1E2761", "1E2761", "DC2626"]):
        box = slide.shapes.add_shape(1, Inches(0.5 + i), Inches(1),
                                     Inches(0.8), Inches(0.8))
        box.fill.solid()
        box.fill.fore_color.rgb = RGBColor.from_string(hexval)
    deck = tmp_path / "choices.pptx"
    prs.save(str(deck))
    pkg = _brandkit_with_distinct_theme(tmp_path)

    decisions = analyze_conflicts(pkg, deck)
    kinds = {d["kind"] for d in decisions}
    assert "color_family" in kinds and "toggle" in kinds
    fam = [d for d in decisions if d["kind"] == "color_family"]
    dominant = next(d for d in fam if d["default"] == "rebrand")
    assert "1E2761" in dominant["swatches"]
    assert dominant.get("mapping", {}).get("1E2761"),         "color decisions must carry an old->new mapping for live preview"
    minority = next(d for d in fam if d["default"] == "keep")
    assert "DC2626" in minority["swatches"]

    # user overrides the defaults: keep the blues, rebrand the red
    choices = {dominant["id"]: "keep", minority["id"]: "rebrand"}
    out = tmp_path / "chosen.pptx"
    retheme_pptx(pkg, deck, out, choices=choices)
    import zipfile as zf
    xml = zf.ZipFile(out).read("ppt/slides/slide1.xml").decode()
    assert "1E2761" in xml, "kept family must stay"
    assert "DC2626" not in xml, "rebranded family must change"


def test_textbox_headings_adopt_brand_title_style(tmp_path):
    """Heading-sized runs in plain text boxes (no placeholder) adopt the
    brandkit title font, size and color; the choice can keep them."""
    from pptx.dml.color import RGBColor
    from pptx.util import Pt

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank: no phs
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(1))
    run = box.text_frame.paragraphs[0].add_run()
    run.text = "Big Georgia Heading"
    run.font.name = "Georgia"
    run.font.size = Pt(28)
    run.font.color.rgb = RGBColor.from_string("1F2937")
    deck = tmp_path / "headings.pptx"
    prs.save(str(deck))

    pkg = _brandkit_with_distinct_theme(tmp_path)
    import json as json_mod
    manifest = json_mod.loads((pkg / "template.json").read_text("utf-8"))
    title_fmt = next(
        ph["format_levels"]["1"] for l in manifest["layouts"]
        for ph in l["placeholders"] if ph["type"] in ("title", "ctrTitle"))

    out = tmp_path / "headed.pptx"
    retheme_pptx(pkg, deck, out)
    branded = Presentation(str(out))
    run = [sh for sh in branded.slides[0].shapes if sh.has_text_frame
           and "Heading" in sh.text_frame.text][0] \
        .text_frame.paragraphs[0].runs[0]
    assert run.font.name == "Verdana"          # brand heading font
    if title_fmt.get("size_pt"):
        assert run.font.size.pt == title_fmt["size_pt"]  # brand title size
    assert run.font.size.pt != 28 or title_fmt.get("size_pt") == 28

    # explicit keep choice preserves the deck's heading styling
    out2 = tmp_path / "kept.pptx"
    retheme_pptx(pkg, deck, out2, choices={"heading_style": "keep",
                                           "font:Georgia": "keep"})
    run2 = [sh for sh in Presentation(str(out2)).slides[0].shapes
            if sh.has_text_frame and "Heading" in sh.text_frame.text][0] \
        .text_frame.paragraphs[0].runs[0]
    assert run2.font.size.pt == 28
    assert run2.font.name == "Georgia"


def test_font_keep_choice_respected_on_headings(tmp_path):
    """A heading-sized run in a foreign font adopts the brand heading font
    when the font decision is 'map', but keeps its own font on 'keep' — the
    heading conversion must not silently override an explicit keep (else the
    font choice has no visible effect on headings)."""
    from pptx.util import Pt

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(1))
    r = box.text_frame.paragraphs[0].add_run()
    r.text = "Foreign Heading"
    r.font.size = Pt(28)
    r.font.name = "Georgia"
    deck = tmp_path / "foreign-heading.pptx"
    prs.save(str(deck))

    pkg = _brandkit_with_distinct_theme(tmp_path)  # brand fonts = Verdana

    def heading_font(out_path, choices):
        retheme_pptx(pkg, deck, out_path, choices=choices)
        run = [sh for sh in Presentation(str(out_path)).slides[0].shapes
               if sh.has_text_frame and "Foreign" in sh.text_frame.text][0] \
            .text_frame.paragraphs[0].runs[0]
        return run.font.name

    assert heading_font(tmp_path / "map.pptx",
                        {"font:Georgia": "map"}) == "Verdana"
    assert heading_font(tmp_path / "keep.pptx",
                        {"font:Georgia": "keep"}) == "Georgia", \
        "keep choice must survive the heading restyle"


def test_textbox_heading_converts_to_title_position(tmp_path):
    """'convert' moves the slide's primary heading box to the brandkit
    title placeholder position; 'adopt' leaves the position alone."""
    from pptx.util import Pt

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(3), Inches(4), Inches(4), Inches(1))
    run = box.text_frame.paragraphs[0].add_run()
    run.text = "Wandering Heading"
    run.font.size = Pt(30)
    # a second, smaller heading that must NOT be moved
    box2 = slide.shapes.add_textbox(Inches(1), Inches(6), Inches(3), Inches(0.6))
    r2 = box2.text_frame.paragraphs[0].add_run()
    r2.text = "Secondary"
    r2.font.size = Pt(21)
    deck = tmp_path / "wandering.pptx"
    prs.save(str(deck))

    pkg = _brandkit_with_distinct_theme(tmp_path)
    import json as json_mod
    manifest = json_mod.loads((pkg / "template.json").read_text("utf-8"))
    title_ph = next(
        ph for l in manifest["layouts"] for ph in l["placeholders"]
        if ph["type"] in ("title", "ctrTitle")
        and ph.get("format_levels", {}).get("1"))
    want_x = round(title_ph["position"]["x_in"] * 914400)
    want_y = round(title_ph["position"]["y_in"] * 914400)

    out = tmp_path / "converted.pptx"
    retheme_pptx(pkg, deck, out)  # default: convert
    slide = Presentation(str(out)).slides[0]
    main = [sh for sh in slide.shapes if sh.has_text_frame
            and "Wandering" in sh.text_frame.text][0]
    second = [sh for sh in slide.shapes if sh.has_text_frame
              and "Secondary" in sh.text_frame.text][0]
    assert main.left == want_x and main.top == want_y, \
        "primary heading must move to the brandkit title position"
    assert second.left == Inches(1), "secondary heading must stay in place"

    out2 = tmp_path / "inplace.pptx"
    retheme_pptx(pkg, deck, out2, choices={"heading_style": "adopt"})
    slide2 = Presentation(str(out2)).slides[0]
    main2 = [sh for sh in slide2.shapes if sh.has_text_frame
             and "Wandering" in sh.text_frame.text][0]
    assert main2.left == Inches(3) and main2.top == Inches(4), \
        "'adopt' must not move the box"


def test_snap_to_exact_primary_and_bullets_in_preview(tmp_path):
    """Accent-level colors snap to the EXACT brand primary; bullet chars
    render in the HTML preview."""
    from pptx.dml.color import RGBColor
    from pptx.util import Pt
    from pptx_template_tool.application.preview_render import render_deck_html

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    circle = slide.shapes.add_shape(9, Inches(0.5), Inches(0.5),
                                    Inches(1), Inches(1))  # OVAL
    circle.fill.solid()
    circle.fill.fore_color.rgb = RGBColor.from_string("1E2761")
    box = slide.shapes.add_textbox(Inches(1), Inches(3), Inches(5), Inches(2))
    tf = box.text_frame
    from lxml import etree
    A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    for i, txt in enumerate(["First point", "Second point"]):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.text = txt
        para.runs[0].font.size = Pt(14)
        ppr = para._p.get_or_add_pPr()
        bu = etree.SubElement(ppr, f"{A}buChar")
        bu.set("char", "■")
    deck = tmp_path / "bullets.pptx"
    prs.save(str(deck))

    pkg = _brandkit_with_distinct_theme(tmp_path)  # primary 10069F
    out = tmp_path / "snapped.pptx"
    retheme_pptx(pkg, deck, out)
    import zipfile as zf
    xml = zf.ZipFile(out).read("ppt/slides/slide1.xml").decode()
    assert "10069F" in xml and "1E2761" not in xml, \
        "accent circle must snap to the exact brand primary"

    html, _ = render_deck_html(pkg, out, "t")
    assert "■" in html, "bullet characters must render in the preview"
    assert 'class="bu"' in html


def test_text_on_colored_shape_stays_in_place_and_white(tmp_path):
    """Heading-sized text inside a colored shape, or in a text box sitting
    on top of one, must NOT move to the title slot and must keep its own
    (white) color; the shape's fill stays governed by color decisions."""
    from pptx.dml.color import RGBColor
    from pptx.util import Pt

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    # colored square with white heading-sized text INSIDE it
    sq = slide.shapes.add_shape(1, Inches(5), Inches(4), Inches(2), Inches(2))
    sq.fill.solid()
    sq.fill.fore_color.rgb = RGBColor.from_string("1E2761")
    r = sq.text_frame.paragraphs[0].add_run()
    r.text = "42%"
    r.font.size = Pt(30)
    r.font.color.rgb = RGBColor.from_string("FFFFFF")
    # transparent text box ON TOP of a second colored square
    sq2 = slide.shapes.add_shape(1, Inches(1), Inches(4), Inches(2), Inches(2))
    sq2.fill.solid()
    sq2.fill.fore_color.rgb = RGBColor.from_string("1E2761")
    box = slide.shapes.add_textbox(Inches(1.2), Inches(4.5),
                                   Inches(1.6), Inches(1))
    br = box.text_frame.paragraphs[0].add_run()
    br.text = "On the square"
    br.font.size = Pt(24)
    br.font.color.rgb = RGBColor.from_string("FFFFFF")
    # a free-standing heading that IS allowed to move to the title slot
    head = slide.shapes.add_textbox(Inches(3), Inches(1), Inches(4), Inches(1))
    hr = head.text_frame.paragraphs[0].add_run()
    hr.text = "Free Heading"
    hr.font.size = Pt(32)
    deck = tmp_path / "onshape.pptx"
    prs.save(str(deck))

    pkg = _brandkit_with_distinct_theme(tmp_path)
    out = tmp_path / "onshape-out.pptx"
    retheme_pptx(pkg, deck, out)  # default: convert

    slide = Presentation(str(out)).slides[0]

    def find(text):
        return [sh for sh in slide.shapes if sh.has_text_frame
                and text in sh.text_frame.text][0]

    sq_out = find("42%")
    assert (sq_out.left, sq_out.top) == (Inches(5), Inches(4)), \
        "text inside a colored shape must stay with the shape"
    box_out = find("On the square")
    assert (box_out.left, box_out.top) == (Inches(1.2), Inches(4.5)), \
        "text box on top of a colored shape must stay in place"
    assert str(sq_out.text_frame.paragraphs[0].runs[0]
               .font.color.rgb) == "FFFFFF"
    assert str(box_out.text_frame.paragraphs[0].runs[0]
               .font.color.rgb) == "FFFFFF"
    # shape fills are still rebranded per the (default) color decisions
    import zipfile as zf
    xml = zf.ZipFile(out).read("ppt/slides/slide1.xml").decode()
    assert "1E2761" not in xml, "shape fill must follow the color decision"


def test_heading_on_shape_keeps_color_even_with_brand_title_color(tmp_path):
    """_apply_heading_style with an explicit brandkit title color: plain
    headings adopt it, headings on colored shapes keep their run color but
    still adopt the brand font/size."""
    from pptx.dml.color import RGBColor
    from pptx.util import Pt
    from pptx_template_tool.application.retheme import _apply_heading_style

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    sq = slide.shapes.add_shape(1, Inches(4), Inches(4), Inches(2), Inches(2))
    sq.fill.solid()
    sq.fill.fore_color.rgb = RGBColor.from_string("10069F")
    r = sq.text_frame.paragraphs[0].add_run()
    r.text = "KPI"
    r.font.size = Pt(28)
    r.font.color.rgb = RGBColor.from_string("FFFFFF")
    plain = slide.shapes.add_textbox(Inches(1), Inches(1),
                                     Inches(4), Inches(1))
    pr = plain.text_frame.paragraphs[0].add_run()
    pr.text = "Plain heading"
    pr.font.size = Pt(28)
    pr.font.color.rgb = RGBColor.from_string("333333")

    _apply_heading_style(slide._element,
                         {"size_pt": 32, "color": "111827"}, "Verdana")

    assert str(r.font.color.rgb) == "FFFFFF", \
        "white text on a colored shape must remain white"
    assert r.font.size.pt == 32 and r.font.name == "Verdana", \
        "font/size restyle still applies to on-shape headings"
    assert str(pr.font.color.rgb) == "111827", \
        "plain headings adopt the brandkit title color"


# --------------------------------------------------------------- edge cases
# Real-deck nuances the retheme must not lose or leave un-rebranded. Each was
# added after auditing which shapes/text/items the restyle engine covers.


def test_retheme_retains_speaker_notes(tmp_path):
    """Speaker notes are slide content and must survive the retheme — they
    were being dropped with the notesSlide relationship."""
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "Slide with notes"
    slide.notes_slide.notes_text_frame.text = "REMEMBER-THIS-NOTE"
    deck = tmp_path / "noted.pptx"
    prs.save(str(deck))

    pkg = _brandkit(tmp_path)
    out = tmp_path / "branded.pptx"
    retheme_pptx(pkg, deck, out)

    branded = Presentation(str(out))
    s = branded.slides[0]
    assert s.has_notes_slide, "notes slide dropped during retheme"
    assert "REMEMBER-THIS-NOTE" in s.notes_slide.notes_text_frame.text


def test_retheme_internal_slide_link_has_no_orphan_slide(tmp_path):
    """A shape hyperlink to another slide (agenda / 'back' button) must be
    repointed, not deep-cloned into an orphaned extra slide part."""
    prs = Presentation()
    s1 = prs.slides.add_slide(prs.slide_layouts[5])
    s1.shapes.title.text = "Agenda"
    s2 = prs.slides.add_slide(prs.slide_layouts[5])
    s2.shapes.title.text = "Target Section"
    box = s1.shapes.add_textbox(Inches(1), Inches(3), Inches(3), Inches(1))
    run = box.text_frame.paragraphs[0].add_run()
    run.text = "Jump to section"
    box.click_action.target_slide = s2
    deck = tmp_path / "linked.pptx"
    prs.save(str(deck))

    pkg = _brandkit(tmp_path)
    out = tmp_path / "branded.pptx"
    retheme_pptx(pkg, deck, out)

    branded = Presentation(str(out))
    assert len(branded.slides) == 2
    # exactly one slide part per real slide: no orphan clone of the target
    with zipfile.ZipFile(out) as z:
        slide_parts = [n for n in z.namelist()
                       if n.startswith("ppt/slides/slide")
                       and n.endswith(".xml")]
    assert len(slide_parts) == 2, \
        f"expected 2 slide parts, found {len(slide_parts)}: {slide_parts}"
    # the link on slide 1 still resolves to an in-deck slide
    link = s1_link = branded.slides[0].shapes[-1].click_action
    assert link.target_slide is not None
    assert link.target_slide in list(branded.slides), \
        "hyperlink points outside the output deck's slide list"


def _inject_into_slide1(deck: Path, sptree_xml: str) -> None:
    """Insert raw OOXML just before </p:spTree> in slide1 of a saved deck."""
    import zipfile as zf
    tmp = deck.with_suffix(".tmp.pptx")
    with zf.ZipFile(deck) as src, zf.ZipFile(tmp, "w",
                                             zf.ZIP_DEFLATED) as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "ppt/slides/slide1.xml":
                data = data.replace(b"</p:spTree>",
                                    sptree_xml.encode() + b"</p:spTree>")
            dst.writestr(name, data)
    tmp.replace(deck)


def test_grouped_heading_not_relocated_offslide(tmp_path):
    """A heading-sized run inside a group (grpSp) uses the group's child
    coordinate space, not slide EMU. 'convert' must not move it to the title
    slot — doing so writes child-space coords and flings it off-slide."""
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[6])  # blank
    deck = tmp_path / "grouped.pptx"
    prs.save(str(deck))
    # a group at (1in,1in) 4x2in with its own child coord space, containing
    # one 30pt heading box at the child origin (0,0)
    A = "http://schemas.openxmlformats.org/drawingml/2006/main"
    group = (
        '<p:grpSp><p:nvGrpSpPr><p:cNvPr id="950" name="Badge Group"/>'
        '<p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr>'
        '<a:xfrm><a:off x="914400" y="914400"/><a:ext cx="3657600" cy="1828800"/>'
        '<a:chOff x="0" y="0"/><a:chExt cx="3657600" cy="1828800"/></a:xfrm>'
        '</p:grpSpPr>'
        '<p:sp><p:nvSpPr><p:cNvPr id="951" name="Badge Heading"/>'
        '<p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr>'
        '<a:xfrm><a:off x="0" y="0"/><a:ext cx="3657600" cy="1828800"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
        '<p:txBody><a:bodyPr/><a:p><a:r><a:rPr lang="en-US" sz="3000"/>'
        '<a:t>Grouped Heading</a:t></a:r></a:p></p:txBody></p:sp></p:grpSp>')
    _inject_into_slide1(deck, group)

    pkg = _brandkit_with_distinct_theme(tmp_path)
    out = tmp_path / "branded.pptx"
    retheme_pptx(pkg, deck, out)  # default: convert

    xml = zipfile.ZipFile(out).read("ppt/slides/slide1.xml").decode()
    from lxml import etree as ET
    root = ET.fromstring(xml.encode())
    nsp = {"a": A, "p":
           "http://schemas.openxmlformats.org/presentationml/2006/main"}
    grp = root.find(".//p:grpSp", nsp)
    assert grp is not None, "group dissolved"
    child_off = grp.find("./p:sp/p:spPr/a:xfrm/a:off", nsp)
    # the grouped heading must keep its child-space origin (0,0); a move to
    # the title slot would overwrite it with slide-absolute EMU
    assert (child_off.get("x"), child_off.get("y")) == ("0", "0"), \
        "grouped heading was relocated using slide coords (off-slide)"


def test_resize_fit_scales_content_to_brand_canvas(tmp_path):
    """With resize='fit', content from a differently-sized deck is uniformly
    scaled onto the brand canvas; the default ('keep') leaves positions."""
    from pptx.util import Emu as E

    prs = Presentation()
    prs.slide_width = E(12192000)   # 16:9 wide source
    prs.slide_height = E(6858000)
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    box = slide.shapes.add_textbox(Inches(4), Inches(2), Inches(3), Inches(1))
    box.text_frame.text = "scale me"
    orig_left, orig_width = box.left, box.width
    deck = tmp_path / "wide.pptx"
    prs.save(str(deck))

    pkg = _brandkit(tmp_path)  # 4:3, 9144000 EMU wide -> factor 0.75

    keep = tmp_path / "keep.pptx"
    retheme_pptx(pkg, deck, keep)  # default: keep positions
    b = [sh for sh in Presentation(str(keep)).slides[0].shapes
         if sh.has_text_frame and "scale me" in sh.text_frame.text][0]
    assert b.left == orig_left, "default must not move content"

    out = tmp_path / "fit.pptx"
    warns = retheme_pptx(pkg, deck, out, choices={"resize": "fit"})
    b2 = [sh for sh in Presentation(str(out)).slides[0].shapes
          if sh.has_text_frame and "scale me" in sh.text_frame.text][0]
    assert abs(b2.left - round(orig_left * 0.75)) <= 1, "position not scaled"
    assert abs(b2.width - round(orig_width * 0.75)) <= 1, "size not scaled"
    assert any("scaled by" in w for w in warns)


def test_custom_table_style_carried_into_brandkit(tmp_path):
    """A table referencing a custom style GUID defined only in the content
    deck must have that definition merged into the brand package (else the
    table renders unstyled); hard-coded source-theme colors in it rebrand."""
    from pptx.util import Inches as In

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    tbl = slide.shapes.add_table(2, 2, In(1), In(1), In(4), In(1.5)).table
    tbl.cell(0, 0).text = "H"
    deck = tmp_path / "tabled.pptx"
    prs.save(str(deck))

    CUSTOM = "{11111111-2222-3333-4444-555555555555}"
    DEFAULT = "{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"
    style_def = (
        f'<a:tblStyle styleId="{CUSTOM}" styleName="Deck Custom">'
        '<a:wholeTbl><a:tcStyle><a:fill><a:solidFill>'
        '<a:srgbClr val="4F81BD"/>'          # source theme accent1 (default)
        '</a:solidFill></a:fill></a:tcStyle></a:wholeTbl></a:tblStyle>')
    # point the table at the custom style, and define it in the deck
    import zipfile as zf
    tmp = deck.with_suffix(".tmp.pptx")
    with zf.ZipFile(deck) as src, zf.ZipFile(tmp, "w",
                                             zf.ZIP_DEFLATED) as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "ppt/slides/slide1.xml":
                data = data.replace(DEFAULT.encode(), CUSTOM.encode())
            elif name == "ppt/tableStyles.xml":
                # the default part is self-closing: expand it to hold the def
                data = data.replace(
                    f'def="{DEFAULT}"/>'.encode(),
                    f'def="{DEFAULT}">{style_def}</a:tblStyleLst>'.encode())
            dst.writestr(name, data)
    tmp.replace(deck)

    pkg = _brandkit_with_distinct_theme(tmp_path)  # accent1 -> 10069F
    out = tmp_path / "branded.pptx"
    warnings = retheme_pptx(pkg, deck, out)

    styles_xml = zipfile.ZipFile(out).read("ppt/tableStyles.xml").decode()
    assert CUSTOM in styles_xml, \
        "custom table style not merged into the brand package"
    # the table's own reference still resolves to the merged style
    slide_xml = zipfile.ZipFile(out).read("ppt/slides/slide1.xml").decode()
    assert CUSTOM in slide_xml
    # hard-coded source accent in the style was rebranded
    assert "10069F" in styles_xml and "4F81BD" not in styles_xml
    assert any("table style" in w for w in warnings)


def test_source_theme_maps_aggregate_all_masters():
    """Color/font remap must cover EVERY source master's theme, not just the
    first — a multi-master corporate deck binds colors to several themes."""
    from pptx_template_tool.application.retheme import (
        _source_theme_color_map, _source_theme_font_map)

    src_themes = [{"accent1": "AAAAAA", "accent2": "111111"},
                  {"accent1": "BBBBBB", "accent2": "CCCCCC"}]
    dest = {"accent1": "10069F", "accent2": "00A3E0"}
    cmap = _source_theme_color_map(src_themes, dest)
    assert cmap["AAAAAA"] == "10069F"          # master 0 accent1
    assert cmap["BBBBBB"] == "10069F"          # master 1 accent1 -> same brand
    assert cmap["CCCCCC"] == "00A3E0"          # master 1 accent2
    assert cmap["111111"] == "00A3E0"          # master 0 accent2

    fmap = _source_theme_font_map(
        [{"minor": "Arial"}, {"minor": "Georgia", "major": "Cambria"}],
        {"minor": "Verdana", "major": "Verdana"})
    assert fmap["Arial"] == "Verdana"
    assert fmap["Georgia"] == "Verdana"
    assert fmap["Cambria"] == "Verdana"


def test_theme_colors_all_covers_every_master(tmp_path):
    """_theme_colors_all returns one theme per slide master."""
    from pptx_template_tool.application.retheme import _theme_colors_all
    prs = Presentation()
    deck = tmp_path / "x.pptx"
    prs.save(str(deck))
    prs = Presentation(str(deck))
    themes = _theme_colors_all(prs)
    assert len(themes) == len(prs.slide_masters) >= 1
    assert themes[0].get("accent1")


def test_convert_moves_kicker_to_subtitle_slot(tmp_path):
    """'convert': secondary text sitting in the title zone moves to the
    brandkit subtitle position with subtitle styling (no collisions)."""
    import json as json_mod
    from pptx.util import Pt

    pkg = _brandkit_with_distinct_theme(tmp_path)
    manifest = json_mod.loads((pkg / "template.json").read_text("utf-8"))
    title_ph = next(
        ph for l in manifest["layouts"] for ph in l["placeholders"]
        if ph["type"] in ("title", "ctrTitle")
        and ph.get("format_levels", {}).get("1"))
    t_x = title_ph["position"]["x_in"]
    t_y = title_ph["position"]["y_in"]

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    heading = slide.shapes.add_textbox(Inches(3), Inches(4),
                                       Inches(4), Inches(1))
    hr = heading.text_frame.paragraphs[0].add_run()
    hr.text = "Main Heading"
    hr.font.size = Pt(30)
    # kicker INSIDE the future title zone -> must be relocated
    kicker = slide.shapes.add_textbox(Inches(t_x + 0.2), Inches(t_y + 0.1),
                                      Inches(2), Inches(0.4))
    kr = kicker.text_frame.paragraphs[0].add_run()
    kr.text = "THE KICKER"
    kr.font.size = Pt(12)
    deck = tmp_path / "kicker.pptx"
    prs.save(str(deck))

    out = tmp_path / "kicked.pptx"
    retheme_pptx(pkg, deck, out)  # default: convert
    slide = Presentation(str(out)).slides[0]
    k = [sh for sh in slide.shapes if sh.has_text_frame
         and "KICKER" in sh.text_frame.text][0]
    h = [sh for sh in slide.shapes if sh.has_text_frame
         and "Main Heading" in sh.text_frame.text][0]
    # heading occupies the title slot; kicker no longer overlaps it
    assert h.top == round(t_y * 914400)
    k_bottom_above = k.top >= h.top + h.height
    k_moved_away = (k.top, k.left) != (round((t_y + 0.1) * 914400),
                                       round((t_x + 0.2) * 914400))
    assert k_moved_away and (k_bottom_above or k.top != h.top), \
        "kicker must be relocated out of the title zone"
    # kicker got subtitle styling (size from the brandkit subtitle format)
    sub_fmt = next(
        (ph["format_levels"]["1"] for l in manifest["layouts"]
         for ph in l["placeholders"]
         if ph["type"] == "subTitle" and ph.get("format_levels", {}).get("1")),
        {"size_pt": 14})
    kr = k.text_frame.paragraphs[0].runs[0]
    if sub_fmt.get("size_pt"):
        assert kr.font.size.pt == sub_fmt["size_pt"]
