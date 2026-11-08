"""Fictional "Lumen & Co." brand template, generated from code.

Used by the browser smoke test (e2e/) and the README screenshot script
(scripts/screenshots.py). It is synthetic on purpose: never put a real
company's template in tests, fixtures or public screenshots.

    python tests/fixtures/lumen_template.py out.pptx
"""

from __future__ import annotations

import sys
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt

NAVY, TEAL, CORAL, SAND = "14213D", "1B998B", "F46036", "F4EFE6"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"


def build(out: Path) -> Path:
    """Write the template (4:3, matching examples/demo-content.pptx)."""
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(10), Inches(7.5)
    W, H = prs.slide_width, prs.slide_height
    master = prs.slide_master
    # python-pptx can only add shapes to slides; build them on a throwaway
    # slide and move the XML into the master / layout shape trees.
    scratch = prs.slides.add_slide(master.slide_layouts[6])

    def add(owner, kind, *args):
        shape = getattr(scratch.shapes, kind)(*args)
        el = shape._element
        el.getparent().remove(el)
        owner.shapes._spTree.append(el)
        return shape

    def rect(owner, x, y, w, h, color, geom=MSO_SHAPE.RECTANGLE, name=None):
        s = add(owner, "add_shape", geom, x, y, w, h)
        s.fill.solid()
        s.fill.fore_color.rgb = RGBColor.from_string(color)
        s.line.fill.background()
        if name:
            s.name = name
        el = s._element  # behind the placeholders
        tree = el.getparent()
        tree.remove(el)
        tree.insert(2, el)

    def logo(owner, x, y, color):
        tb = add(owner, "add_textbox", x, y, Inches(2.4), Inches(0.5))
        tb.name = "Logo"
        run = tb.text_frame.paragraphs[0].add_run()
        run.text = "LUMEN & CO."
        run.font.size, run.font.bold, run.font.name = Pt(16), True, "Georgia"
        run.font.color.rgb = RGBColor.from_string(color)
        dot = add(owner, "add_shape", MSO_SHAPE.OVAL, x - Inches(0.32),
                  y + Inches(0.14), Inches(0.22), Inches(0.22))
        dot.fill.solid()
        dot.fill.fore_color.rgb = RGBColor.from_string(CORAL)
        dot.line.fill.background()
        dot.name = "Logo mark"

    def white_text(layout):
        for ph in layout.placeholders:
            txb = ph._element.find(f"{{{P}}}txBody")
            if txb is None:
                continue
            ls = txb.find(f"{{{A}}}lstStyle")
            if ls is None:
                ls = etree.Element(f"{{{A}}}lstStyle")
                txb.insert(1, ls)
            for child in list(ls):
                ls.remove(child)
            lvl = etree.SubElement(ls, f"{{{A}}}lvl1pPr", marL="0", indent="0")
            etree.SubElement(lvl, f"{{{A}}}buNone")
            fill = etree.SubElement(etree.SubElement(lvl, f"{{{A}}}defRPr"),
                                    f"{{{A}}}solidFill")
            etree.SubElement(fill, f"{{{A}}}srgbClr", val="FFFFFF")

    # theme colors + fonts
    theme_part = next(r.target_part for r in master.part.rels.values()
                      if r.reltype.endswith("/theme"))
    theme = etree.fromstring(theme_part.blob)
    scheme = theme.find(f".//{{{A}}}clrScheme")
    scheme.set("name", "Lumen")
    for slot, hexval in {"dk2": NAVY, "lt2": SAND, "accent1": TEAL, "accent2": CORAL,
                         "accent3": "FFB627", "accent4": "2E4057",
                         "accent5": "8AC6D0", "accent6": "6C757D"}.items():
        el = scheme.find(f"{{{A}}}{slot}")
        for child in list(el):
            el.remove(child)
        etree.SubElement(el, f"{{{A}}}srgbClr", val=hexval)
    for tag, face in (("majorFont", "Georgia"), ("minorFont", "Segoe UI")):
        theme.find(f".//{{{A}}}{tag}/{{{A}}}latin").set("typeface", face)
    theme_part._blob = etree.tostring(theme, xml_declaration=True,
                                      encoding="UTF-8", standalone=True)

    rect(master, 0, H - Inches(0.12), W, Inches(0.12), TEAL, name="Footer rule")
    for layout in master.slide_layouts:
        fill = layout.background.fill
        fill.solid()
        if layout.name == "Title Slide":
            fill.fore_color.rgb = RGBColor.from_string(NAVY)
            rect(layout, Inches(6.9), 0, W - Inches(6.9), H, TEAL, name="Side panel")
            rect(layout, Inches(7.4), Inches(1.0), Inches(2.1), Inches(2.1), CORAL,
                 MSO_SHAPE.OVAL, name="Accent circle")
            logo(layout, Inches(1.1), Inches(0.6), "FFFFFF")
            for ph in layout.placeholders:
                ph.left, ph.width = Inches(0.8), Inches(5.6)
            white_text(layout)
        elif layout.name == "Section Header":
            fill.fore_color.rgb = RGBColor.from_string(TEAL)
            rect(layout, Inches(0.8), Inches(3.6), Inches(1.6), Inches(0.1), CORAL,
                 name="Accent bar")
            white_text(layout)
        else:
            fill.fore_color.rgb = RGBColor.from_string(SAND)
            rect(layout, 0, 0, Inches(0.25), H, CORAL, name="Edge bar")
            logo(layout, W - Inches(2.4), H - Inches(0.75), NAVY)

    ids = prs.slides._sldIdLst  # drop the throwaway slide
    prs.part.drop_rel(ids[0].rId)
    ids.remove(ids[0])
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(out)
    return out


if __name__ == "__main__":
    print(build(Path(sys.argv[1] if len(sys.argv) > 1 else "lumen-template.pptx")))
