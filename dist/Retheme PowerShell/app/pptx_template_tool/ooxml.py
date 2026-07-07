"""Shared OOXML helpers: namespaces, color resolution, transform math."""

from __future__ import annotations

import re

from lxml import etree

_HEX6 = re.compile(r"[0-9A-Fa-f]{6}")

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "asvg": "http://schemas.microsoft.com/office/drawing/2016/SVG/main",
}


def q(tag: str) -> str:
    """'a:solidFill' -> '{ns}solidFill'"""
    prefix, local = tag.split(":")
    return f"{{{NS[prefix]}}}{local}"


def find(el, path: str):
    return el.find(path, NS) if el is not None else None


def findall(el, path: str):
    return el.findall(path, NS) if el is not None else []


# ---------------------------------------------------------------- colors

# Standard PowerPoint color map: master's p:clrMap maps slot names used in
# schemeClr references (bg1/tx1/bg2/tx2) to theme slots (lt1/dk1/lt2/dk2).
DEFAULT_CLR_MAP = {
    "bg1": "lt1", "tx1": "dk1", "bg2": "lt2", "tx2": "dk2",
    "accent1": "accent1", "accent2": "accent2", "accent3": "accent3",
    "accent4": "accent4", "accent5": "accent5", "accent6": "accent6",
    "hlink": "hlink", "folHlink": "folHlink",
}


def parse_clr_map(master_el) -> dict[str, str]:
    m = dict(DEFAULT_CLR_MAP)
    cm = find(master_el, ".//p:clrMap")
    if cm is not None:
        for slot in ("bg1", "tx1", "bg2", "tx2"):
            v = cm.get(slot)
            if v:
                m[slot] = v
    return m


def _apply_mods(hex_color: str, color_el) -> str:
    """Apply lumMod/lumOff/shade/tint children to a hex color (approximation)."""
    r = int(hex_color[0:2], 16) / 255
    g = int(hex_color[2:4], 16) / 255
    b = int(hex_color[4:6], 16) / 255

    def pct(child_tag):
        c = find(color_el, child_tag)
        if c is not None:
            return int(c.get("val")) / 100000
        return None

    shade = pct("a:shade")
    if shade is not None:
        r, g, b = r * shade, g * shade, b * shade
    tint = pct("a:tint")
    if tint is not None:
        r = r * tint + (1 - tint)
        g = g * tint + (1 - tint)
        b = b * tint + (1 - tint)
    lum_mod = pct("a:lumMod")
    lum_off = pct("a:lumOff")
    if lum_mod is not None or lum_off is not None:
        # crude HSL luminance scale, good enough for review previews
        mod = lum_mod if lum_mod is not None else 1.0
        off = lum_off if lum_off is not None else 0.0
        r = min(1.0, r * mod + off)
        g = min(1.0, g * mod + off)
        b = min(1.0, b * mod + off)
    return "%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def resolve_color(color_parent, theme_colors: dict[str, str],
                  clr_map: dict[str, str]) -> dict | None:
    """Resolve the first child color element (srgbClr/schemeClr/sysClr/...)
    of `color_parent` (e.g. an a:solidFill) to {"hex", "alpha", "theme_slot"}.
    """
    if color_parent is None:
        return None
    for child in color_parent:
        tag = etree.QName(child).localname
        hex_val, slot = None, None
        if tag == "srgbClr":
            hex_val = child.get("val", "").upper()
        elif tag == "sysClr":
            hex_val = (child.get("lastClr") or "000000").upper()
        elif tag == "schemeClr":
            ref = child.get("val")
            slot = clr_map.get(ref, ref)
            hex_val = theme_colors.get(slot)
        elif tag == "prstClr":
            # rare in templates; map a few common names
            named = {"black": "000000", "white": "FFFFFF", "red": "FF0000",
                     "green": "008000", "blue": "0000FF", "gray": "808080"}
            hex_val = named.get(child.get("val", ""), "000000")
        if hex_val:
            # Validate BEFORE _apply_mods: it does int(hex[:2], 16) and would
            # crash on a malformed value. This also stops untrusted colors
            # (a crafted srgbClr val like `"><script>`) reaching a CSS/SVG
            # sink downstream — only clean 6-digit hex may pass.
            if not _HEX6.fullmatch(hex_val):
                continue
            hex_val = _apply_mods(hex_val, child)
            alpha_el = find(child, "a:alpha")
            alpha = int(alpha_el.get("val")) / 100000 if alpha_el is not None else 1.0
            return {"hex": hex_val, "alpha": round(alpha, 3), "theme_slot": slot}
    return None


# ---------------------------------------------------------------- transforms

def parse_xfrm(sp_pr) -> dict | None:
    """Parse a:xfrm -> dict of EMU offsets/extents plus rotation/flip."""
    xfrm = find(sp_pr, "a:xfrm")
    if xfrm is None:
        return None
    off = find(xfrm, "a:off")
    ext = find(xfrm, "a:ext")
    out = {
        "x": int(off.get("x")) if off is not None else None,
        "y": int(off.get("y")) if off is not None else None,
        "cx": int(ext.get("cx")) if ext is not None else None,
        "cy": int(ext.get("cy")) if ext is not None else None,
        "rot": int(xfrm.get("rot", 0)),
        "flipH": xfrm.get("flipH") == "1",
        "flipV": xfrm.get("flipV") == "1",
    }
    ch_off = find(xfrm, "a:chOff")
    ch_ext = find(xfrm, "a:chExt")
    if ch_off is not None:
        out["ch_x"] = int(ch_off.get("x"))
        out["ch_y"] = int(ch_off.get("y"))
    if ch_ext is not None:
        out["ch_cx"] = int(ch_ext.get("cx"))
        out["ch_cy"] = int(ch_ext.get("cy"))
    return out


def compose_group_transform(child_xfrm: dict, group_xfrm: dict) -> dict:
    """Map a child shape's transform through its parent group's transform
    (group child-space -> slide space), including group flipH/flipV which
    mirror child positions within the group box. Group rotation is not
    composed (rare in templates).
    """
    if not group_xfrm:
        return child_xfrm
    gx, gy = group_xfrm.get("x") or 0, group_xfrm.get("y") or 0
    gcx, gcy = group_xfrm.get("cx") or 0, group_xfrm.get("cy") or 0
    chx, chy = group_xfrm.get("ch_x", gx), group_xfrm.get("ch_y", gy)
    chcx = group_xfrm.get("ch_cx") or gcx or 1
    chcy = group_xfrm.get("ch_cy") or gcy or 1
    sx = gcx / chcx if chcx else 1
    sy = gcy / chcy if chcy else 1
    flip_h = bool(group_xfrm.get("flipH"))
    flip_v = bool(group_xfrm.get("flipV"))
    out = dict(child_xfrm)
    w = (child_xfrm.get("cx") or 0) * sx
    h = (child_xfrm.get("cy") or 0) * sy
    if child_xfrm.get("x") is not None:
        x_rel = (child_xfrm["x"] - chx) * sx
        y_rel = (child_xfrm["y"] - chy) * sy
        if flip_h:
            x_rel = gcx - x_rel - w
        if flip_v:
            y_rel = gcy - y_rel - h
        out["x"] = round(gx + x_rel)
        out["y"] = round(gy + y_rel)
    if child_xfrm.get("cx") is not None:
        out["cx"] = round(w)
        out["cy"] = round(h)
    if flip_h:
        out["flipH"] = not child_xfrm.get("flipH", False)
    if flip_v:
        out["flipV"] = not child_xfrm.get("flipV", False)
    return out
