"""Fidelity audit: verify that every visible element of every layout in the
source template is accounted for in the extracted package.

Deliberately re-derives visibility and geometry from the raw XML with its own
minimal logic (rather than reusing the extractor's code paths), so extractor
blind spots show up as mismatches instead of being mirrored here.

Usage:  python -m pptx_template_tool.cli audit template.potx package-dir/
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}
EMU = 914400
TOL = 0.06  # inches


@dataclass
class Expected:
    name: str
    kind: str          # placeholder | shape | pic | mask
    ph_type: str | None
    bbox: tuple | None  # (x, y, w, h) inches, None if inherited
    has_text: bool = False
    notes: list = field(default_factory=list)


def _f(el, path):
    return el.find(path, NS)


def _bbox(xfrm_el):
    off, ext = _f(xfrm_el, "a:off"), _f(xfrm_el, "a:ext")
    if off is None or ext is None:
        return None
    return (int(off.get("x")) / EMU, int(off.get("y")) / EMU,
            int(ext.get("cx")) / EMU, int(ext.get("cy")) / EMU)


def _walk(container, ctx, out: list[Expected], skip_placeholders=False):
    """ctx: group mapping tuple, see recursion below. skip_placeholders is
    used for the master tree: master placeholders are formatting prototypes
    and are never rendered on slides."""
    for child in container:
        tag = etree.QName(child).localname
        if tag not in ("sp", "pic", "cxnSp", "grpSp"):
            continue
        cnvpr = child.find(f".//{{{NS['p']}}}cNvPr")
        name = cnvpr.get("name") if cnvpr is not None else "?"
        if cnvpr is not None and cnvpr.get("hidden") == "1":
            continue

        sp_pr = _f(child, "p:spPr") if tag != "grpSp" else _f(child, "p:grpSpPr")
        xfrm = _f(sp_pr, "a:xfrm") if sp_pr is not None else None
        bbox = _bbox(xfrm) if xfrm is not None else None
        if bbox is not None and ctx is not None:
            ox, oy, sx, sy, fh, fv, gw, gh, chx0, chy0 = ctx
            x, y, w, h = bbox
            x, y = (x - chx0) * sx, (y - chy0) * sy
            w, h = w * sx, h * sy
            if fh:
                x = gw - x - w
            if fv:
                y = gh - y - h
            bbox = (ox + x, oy + y, w, h)

        if tag == "grpSp":
            if xfrm is None:
                continue
            ch_off, ch_ext = _f(xfrm, "a:chOff"), _f(xfrm, "a:chExt")
            gx, gy, gw, gh = bbox
            chx = int(ch_off.get("x")) / EMU if ch_off is not None else gx
            chy = int(ch_off.get("y")) / EMU if ch_off is not None else gy
            chw = int(ch_ext.get("cx")) / EMU if ch_ext is not None else gw
            chh = int(ch_ext.get("cy")) / EMU if ch_ext is not None else gh
            sx = gw / chw if chw else 1
            sy = gh / chh if chh else 1
            new_ctx = (gx, gy, sx, sy,
                       xfrm.get("flipH") == "1", xfrm.get("flipV") == "1",
                       gw, gh, chx, chy)
            _walk(child, new_ctx, out, skip_placeholders)
            continue

        ph = child.find(f".//{{{NS['p']}}}ph")
        text = "".join(t.text or "" for t in child.iter(f"{{{NS['a']}}}t")).strip()

        if ph is not None:
            if not skip_placeholders:
                out.append(Expected(name, "placeholder", ph.get("type", "obj"),
                                    bbox, bool(text)))
            continue
        if tag == "pic":
            out.append(Expected(name, "pic", None, bbox))
            continue
        if child.get("useBgFill") == "1":
            out.append(Expected(name, "mask", None, bbox))
            continue
        ln = _f(sp_pr, "a:ln")
        ln_paints = ln is not None and _f(ln, "a:noFill") is None
        fill_paints = any(_f(sp_pr, p) is not None for p in
                          ("a:solidFill", "a:gradFill", "a:blipFill"))
        no_fill = _f(sp_pr, "a:noFill") is not None
        has_paint = fill_paints or ln_paints or (
            not no_fill and _f(child, "p:style") is not None)
        has_geom = (_f(sp_pr, "a:prstGeom") is not None or
                    _f(sp_pr, "a:custGeom") is not None)
        if has_paint and has_geom:
            out.append(Expected(name, "shape", None, bbox, bool(text)))
        elif text:
            out.append(Expected(name, "text", None, bbox, True))


def _mostly_off_canvas(bbox, slide_w, slide_h) -> bool:
    if bbox is None:
        return False
    x, y, w, h = bbox
    if x + w < 0 or x > slide_w or y + h < 0 or y > slide_h:
        return True
    fx = (min(x + w, slide_w) - max(x, 0)) / w if w else 1.0
    fy = (min(y + h, slide_h) - max(y, 0)) / h if h else 1.0
    return fx * fy < 0.4


def _close(b1, b2) -> bool:
    return all(abs(a - b) <= TOL for a, b in zip(b1, b2))


def audit_package(source: str | Path, package_dir: str | Path) -> dict:
    """Returns {"layouts": {name: {"matched": n, "missing": [...],
    "notes": [...]}}, "total_missing": n}."""
    source, package_dir = Path(source), Path(package_dir)
    manifest = json.loads(
        (package_dir / "template.json").read_text(encoding="utf-8"))
    slide_w = manifest["slide_geometry"]["width_in"]
    slide_h = manifest["slide_geometry"]["height_in"]
    assets = {a["asset_id"]: a for a in manifest["assets"]}
    layouts = {l["name"]: l for l in manifest["layouts"]}

    z = zipfile.ZipFile(source)
    # map layout xml -> cSld name
    report: dict = {"layouts": {}, "total_missing": 0}
    master_root = etree.fromstring(z.read("ppt/slideMasters/slideMaster1.xml"))

    for i in range(1, 200):
        try:
            data = z.read(f"ppt/slideLayouts/slideLayout{i}.xml")
        except KeyError:
            break
        root = etree.fromstring(data)
        lname = root.find(".//{*}cSld").get("name") or f"layout{i}"
        rec = layouts.get(lname)
        if rec is None:
            report["layouts"][lname] = {"matched": 0, "missing": [],
                                        "notes": ["layout missing from manifest"]}
            continue

        expected: list[Expected] = []
        if root.get("showMasterSp", "1") != "0":
            _walk(master_root.find(".//p:cSld/p:spTree", NS), None, expected,
                  skip_placeholders=True)
        _walk(root.find(".//p:cSld/p:spTree", NS), None, expected)

        # actual bboxes available for matching in the package
        actual: list[tuple] = []
        for ph in rec["placeholders"]:
            if ph.get("position") and ph.get("size"):
                actual.append((ph["position"]["x_in"], ph["position"]["y_in"],
                               ph["size"]["width_in"], ph["size"]["height_in"]))
            else:
                actual.append(None)  # inherited: matched by presence
        ph_types = [p["type"] for p in rec["placeholders"]]
        for aid in rec["static_assets"]:
            a = assets.get(aid)
            if a and a.get("position") and a.get("size"):
                actual.append((a["position"]["x_in"], a["position"]["y_in"],
                               a["size"]["width_in"], a["size"]["height_in"]))
        actual_texts = [
            (t["position"]["x_in"], t["position"]["y_in"],
             t["size"]["width_in"], t["size"]["height_in"])
            for t in rec.get("static_texts", [])]

        matched, missing, notes = 0, [], []
        for exp in expected:
            if exp.bbox is not None and exp.bbox[2] == 0 and exp.bbox[3] == 0:
                continue  # zero-extent marker shapes are invisible
            if _mostly_off_canvas(exp.bbox, slide_w, slide_h):
                continue
            if exp.kind == "placeholder":
                if exp.ph_type in ("dt", "ftr", "sldNum"):
                    continue  # footer strip: matched by type only
                if exp.ph_type in ph_types:
                    matched += 1
                else:
                    missing.append(f'placeholder {exp.ph_type} "{exp.name}"')
                continue
            if exp.kind == "text":
                if exp.bbox is None or any(_close(exp.bbox, b)
                                           for b in actual_texts):
                    matched += 1
                else:
                    missing.append(f'static text "{exp.name}"')
                continue
            if exp.bbox is None:
                continue
            if any(b is not None and _close(exp.bbox, b) for b in actual):
                matched += 1
            else:
                missing.append(
                    f'{exp.kind} "{exp.name}" at '
                    f'({exp.bbox[0]:.2f},{exp.bbox[1]:.2f}) '
                    f'{exp.bbox[2]:.2f}x{exp.bbox[3]:.2f}')
            if exp.kind == "shape" and exp.has_text and \
                    not any(_close(exp.bbox, b) for b in actual_texts):
                notes.append(f'shape "{exp.name}" contains text that is not '
                             f'carried into the package')

        report["layouts"][lname] = {"matched": matched, "missing": missing,
                                    "notes": notes}
        report["total_missing"] += len(missing)
    return report


def print_report(report: dict) -> None:
    for lname, r in report["layouts"].items():
        status = "OK " if not r["missing"] and not r["notes"] else "!! "
        print(f'{status}{lname}: {r["matched"]} matched, '
              f'{len(r["missing"])} missing')
        for m in r["missing"]:
            print(f"     MISSING {m}")
        for n in r["notes"]:
            print(f"     NOTE    {n}")
    print(f'\ntotal missing: {report["total_missing"]}')
