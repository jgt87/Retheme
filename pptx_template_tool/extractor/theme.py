"""Theme extraction: color scheme, font scheme, format scheme, and
semantic color-role inference based on actual usage across layouts."""

from __future__ import annotations

from collections import Counter

from lxml import etree

from ..ooxml import NS, find, findall, resolve_color
from ..units import angle_60k_to_deg

THEME_SLOTS = ["dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3",
               "accent4", "accent5", "accent6", "hlink", "folHlink"]


def parse_theme_colors(theme_el) -> dict[str, str]:
    """theme XML -> {slot: hex}."""
    out = {}
    scheme = find(theme_el, ".//a:clrScheme")
    if scheme is None:
        return out
    for slot in THEME_SLOTS:
        slot_el = find(scheme, f"a:{slot}")
        if slot_el is None:
            continue
        srgb = find(slot_el, "a:srgbClr")
        sysc = find(slot_el, "a:sysClr")
        if srgb is not None:
            out[slot] = srgb.get("val", "").upper()
        elif sysc is not None:
            out[slot] = (sysc.get("lastClr") or "000000").upper()
    return out


def parse_font_scheme(theme_el) -> dict:
    scheme = find(theme_el, ".//a:fontScheme")
    out = {"heading": None, "body": None}
    if scheme is None:
        return out
    major = find(scheme, "a:majorFont/a:latin")
    minor = find(scheme, "a:minorFont/a:latin")
    if major is not None:
        out["heading"] = major.get("typeface")
    if minor is not None:
        out["body"] = minor.get("typeface")
    return out


def _summarize_gradient(grad_el, theme_colors, clr_map) -> dict:
    stops = []
    for gs in findall(grad_el, "a:gsLst/a:gs"):
        c = resolve_color(gs, theme_colors, clr_map)
        if c:
            stops.append({"pos": int(gs.get("pos", 0)) / 100000, **c})
    stops.sort(key=lambda s: s["pos"])  # document order may be reversed
    lin = find(grad_el, "a:lin")
    return {
        "type": "gradient",
        "stops": stops,
        "angle_deg": angle_60k_to_deg(int(lin.get("ang", 0))) if lin is not None else 0,
    }


def parse_fmt_scheme(theme_el, theme_colors, clr_map) -> dict:
    """Capture fill/line/effect presets used by style references (bgRef etc.)."""
    scheme = find(theme_el, ".//a:fmtScheme")
    out = {"fills": [], "bg_fills": [], "effects": []}
    if scheme is None:
        return out

    def fill_summary(fill_el):
        tag = etree.QName(fill_el).localname
        if tag == "solidFill":
            c = resolve_color(fill_el, theme_colors, clr_map)
            return {"type": "solid", **(c or {})}
        if tag == "gradFill":
            return _summarize_gradient(fill_el, theme_colors, clr_map)
        return {"type": tag}

    for lst_name, key in (("a:fillStyleLst", "fills"), ("a:bgFillStyleLst", "bg_fills")):
        lst = find(scheme, lst_name)
        if lst is not None:
            out[key] = [fill_summary(f) for f in lst]

    effect_lst = find(scheme, "a:effectStyleLst")
    if effect_lst is not None:
        for style in findall(effect_lst, "a:effectStyle"):
            shadow = find(style, ".//a:outerShdw")
            out["effects"].append({
                "has_shadow": shadow is not None,
                "shadow_blur_emu": int(shadow.get("blurRad", 0)) if shadow is not None else None,
            })
    return out


# --------------------------------------------------- semantic role inference

def infer_color_roles(theme_colors: dict[str, str], layout_elements: list,
                      clr_map: dict[str, str]) -> list[dict]:
    """Cross-reference where each theme color is actually referenced across
    masters/layouts (theme slot names alone are unreliable).

    Returns the colors list for the manifest:
    [{hex, theme_slot, role, usage: {fill: n, text: n, line: n, background: n}}]
    """
    usage: dict[str, Counter] = {slot: Counter() for slot in theme_colors}
    reverse_map = {v: k for k, v in clr_map.items()}  # theme slot -> ref name

    for root in layout_elements:
        for ref in root.iter(f"{{{NS['a']}}}schemeClr"):
            slot = clr_map.get(ref.get("val"), ref.get("val"))
            if slot not in usage:
                continue
            parent = ref.getparent()
            ptag = etree.QName(parent).localname if parent is not None else ""
            gp = parent.getparent() if parent is not None else None
            gtag = etree.QName(gp).localname if gp is not None else ""
            ggp = gp.getparent() if gp is not None else None
            ggtag = etree.QName(ggp).localname if ggp is not None else ""
            if ptag == "solidFill":
                if gtag in ("rPr", "defRPr", "endParaRPr"):
                    usage[slot]["text"] += 1
                elif gtag == "ln":
                    usage[slot]["line"] += 1
                elif gtag == "bgPr" or ggtag == "bgPr":
                    usage[slot]["background"] += 1
                else:
                    usage[slot]["fill"] += 1
            elif ptag in ("gs",):  # gradient stop
                usage[slot]["fill"] += 1
            elif ptag in ("buClr",):
                usage[slot]["accent_mark"] += 1

    colors = []
    accents_by_fill = sorted(
        (s for s in theme_colors if s.startswith("accent")),
        key=lambda s: -(usage[s]["fill"] + usage[s]["text"] + usage[s]["line"]),
    )
    for slot, hex_val in theme_colors.items():
        u = usage[slot]
        role = "accent"
        if slot in ("lt1", "lt2") or u["background"] > max(u["fill"], u["text"]):
            role = "background"
        elif slot in ("dk1", "dk2"):
            role = "text"
        elif slot in ("hlink", "folHlink"):
            role = "hyperlink"
        elif slot.startswith("accent"):
            if accents_by_fill and slot == accents_by_fill[0]:
                role = "primary"
            elif len(accents_by_fill) > 1 and slot == accents_by_fill[1]:
                role = "secondary"
        total = sum(u.values())
        colors.append({
            "hex": hex_val,
            "theme_slot": slot,
            "scheme_ref": reverse_map.get(slot, slot),
            "role": role,
            "usage": dict(u),
            "confidence": "high" if total >= 3 or slot in ("dk1", "lt1") else "low",
        })
    return colors
