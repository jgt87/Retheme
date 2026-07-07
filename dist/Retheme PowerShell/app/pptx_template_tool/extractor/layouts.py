"""Per-layout extraction: placeholder inventory (position, size, z-order,
text formatting with master/theme inheritance) and background definition."""

from __future__ import annotations

import re

from lxml import etree

from ..ooxml import NS, find, findall, parse_xfrm, q, resolve_color
from ..units import centipt_to_pt, emu_to_in, emu_to_pct
from .theme import _summarize_gradient

# p:sldLayout/@type -> human purpose. "cust" falls back to name heuristics.
LAYOUT_TYPE_PURPOSE = {
    "title": "Title Slide",
    "tx": "Title and Text",
    "obj": "Title and Content",
    "twoObj": "Two Content",
    "twoTxTwoObj": "Comparison",
    "secHead": "Section Header",
    "titleOnly": "Title Only",
    "blank": "Blank",
    "objTx": "Content with Caption",
    "picTx": "Picture with Caption",
    "vertTx": "Vertical Text",
    "vertTitleAndTx": "Vertical Title and Text",
}

_NAME_HINTS = [
    (r"title|cover|voorblad", "Title Slide"),
    (r"section|chapter|divider|hoofdstuk", "Section Header"),
    (r"two|2\s*content|comparison|vergelijk", "Two Content"),
    (r"agenda|toc|content(s)?\b|inhoud", "Agenda / Table of Contents"),
    (r"quote|citaat", "Quote"),
    (r"thank|closing|end|afsluit", "Closing Slide"),
    (r"blank|empty|leeg", "Blank"),
    (r"photo|picture|image|foto", "Picture Layout"),
]


def infer_purpose(layout_type: str | None, name: str) -> str:
    if layout_type and layout_type in LAYOUT_TYPE_PURPOSE:
        return LAYOUT_TYPE_PURPOSE[layout_type]
    low = (name or "").lower()
    for pattern, purpose in _NAME_HINTS:
        if re.search(pattern, low):
            return purpose
    return "General Content"


# ------------------------------------------------------------- placeholders

def _ph_info(sp):
    ph = find(sp, ".//p:nvSpPr/p:nvPr/p:ph")
    if ph is None:
        return None
    return {"type": ph.get("type", "obj"), "idx": int(ph.get("idx", 0))}


def _match_master_ph(master_el, ph_type: str, idx: int):
    """Find the master placeholder a layout placeholder inherits from."""
    body_like = {"body", "subTitle", "obj", "pic", "chart", "tbl", "dgm", "media", "clipArt"}
    title_like = {"title", "ctrTitle"}
    candidates = []
    for sp in findall(master_el, ".//p:cSld/p:spTree/p:sp"):
        info = _ph_info(sp)
        if info is None:
            continue
        if info["type"] == ph_type and info["idx"] == idx:
            return sp  # exact match wins
        if ph_type in title_like and info["type"] in title_like:
            candidates.append(sp)
        elif ph_type in body_like and info["type"] in body_like:
            candidates.append(sp)
        elif ph_type in ("dt", "ftr", "sldNum") and info["type"] == ph_type:
            candidates.append(sp)
    return candidates[0] if candidates else None


def _rpr_props(rpr, theme_colors, clr_map, font_scheme):
    """Extract run-property formatting from an rPr/defRPr element."""
    if rpr is None:
        return {}
    out = {}
    if rpr.get("sz"):
        out["size_pt"] = centipt_to_pt(int(rpr.get("sz")))
    if rpr.get("b") is not None:
        out["bold"] = rpr.get("b") == "1"
    if rpr.get("i") is not None:
        out["italic"] = rpr.get("i") == "1"
    latin = find(rpr, "a:latin")
    if latin is not None:
        face = latin.get("typeface", "")
        if face == "+mj-lt":
            face = font_scheme.get("heading")
        elif face == "+mn-lt":
            face = font_scheme.get("body")
        if face:
            out["font"] = face
    fill = find(rpr, "a:solidFill")
    color = resolve_color(fill, theme_colors, clr_map)
    if color:
        out["color"] = color["hex"]
        if color.get("theme_slot"):
            out["color_theme_slot"] = color["theme_slot"]
    return out


def _ppr_props(ppr, theme_colors, clr_map):
    """Paragraph-level properties: alignment, bullet, indent."""
    if ppr is None:
        return {}
    out = {}
    algn = ppr.get("algn")
    if algn:
        out["align"] = {"l": "left", "ctr": "center", "r": "right",
                        "just": "justify"}.get(algn, algn)
    if ppr.get("marL"):
        out["indent_in"] = emu_to_in(int(ppr.get("marL")))
    if find(ppr, "a:buNone") is not None:
        out["bullet"] = None
    else:
        bu_char = find(ppr, "a:buChar")
        bu_auto = find(ppr, "a:buAutoNum")
        if bu_char is not None:
            out["bullet"] = {"kind": "char", "char": bu_char.get("char")}
        elif bu_auto is not None:
            out["bullet"] = {"kind": "number", "format": bu_auto.get("type")}
    return out


def _lst_style_levels(container, theme_colors, clr_map, font_scheme,
                      max_levels: int = 3) -> dict[int, dict]:
    """Parse a:lvlNpPr children of an a:lstStyle (or master txStyles style)."""
    levels: dict[int, dict] = {}
    if container is None:
        return levels
    for n in range(1, max_levels + 1):
        lvl = find(container, f"a:lvl{n}pPr")
        if lvl is None:
            continue
        props = _ppr_props(lvl, theme_colors, clr_map)
        props.update(_rpr_props(find(lvl, "a:defRPr"), theme_colors, clr_map, font_scheme))
        if props:
            levels[n] = props
    return levels


def _merge_levels(*level_dicts: dict[int, dict]) -> dict[int, dict]:
    """Merge level formatting, later dicts win per-key."""
    out: dict[int, dict] = {}
    for d in level_dicts:
        for lvl, props in d.items():
            merged = dict(out.get(lvl, {}))
            merged.update({k: v for k, v in props.items() if v is not None or k == "bullet"})
            out[lvl] = merged
    return out


def _resolve_ph_format(ph_type, layout_sp, master_sp, master_el,
                       theme_colors, clr_map, font_scheme) -> dict[int, dict]:
    """Resolution order: theme defaults < master txStyles < master ph lstStyle
    < layout ph lstStyle."""
    title_like = ph_type in ("title", "ctrTitle")
    style_name = "p:titleStyle" if title_like else (
        "p:bodyStyle" if ph_type in ("body", "subTitle", "obj") else "p:otherStyle")
    tx_styles = find(master_el, f".//p:txStyles/{style_name}")

    base_font = font_scheme.get("heading") if title_like else font_scheme.get("body")
    defaults = {1: {"font": base_font}} if base_font else {}

    master_lst = find(master_sp, ".//a:lstStyle") if master_sp is not None else None
    layout_lst = find(layout_sp, ".//a:lstStyle")
    merged = _merge_levels(
        defaults,
        _lst_style_levels(tx_styles, theme_colors, clr_map, font_scheme),
        _lst_style_levels(master_lst, theme_colors, clr_map, font_scheme),
        _lst_style_levels(layout_lst, theme_colors, clr_map, font_scheme),
    )
    # inherit missing font down levels from level 1
    if 1 in merged:
        for n, props in merged.items():
            if n != 1:
                for key in ("font", "color"):
                    props.setdefault(key, merged[1].get(key))
    return merged


def extract_placeholders(layout_el, master_el, slide_w, slide_h,
                         theme_colors, clr_map, font_scheme) -> list[dict]:
    placeholders = []
    sp_tree = find(layout_el, ".//p:cSld/p:spTree")
    z = 0
    for sp in sp_tree:
        if etree.QName(sp).localname != "sp":
            if etree.QName(sp).localname in ("pic", "grpSp", "graphicFrame", "cxnSp"):
                z += 1
            continue
        z += 1
        info = _ph_info(sp)
        if info is None:
            continue  # non-placeholder shapes handled by asset extraction
        name_el_pre = find(sp, ".//p:nvSpPr/p:cNvPr")
        if name_el_pre is not None and name_el_pre.get("hidden") == "1":
            continue  # hidden placeholders are never rendered
        master_sp = _match_master_ph(master_el, info["type"], info["idx"])
        xfrm = parse_xfrm(find(sp, "p:spPr"))
        if (xfrm is None or xfrm.get("x") is None) and master_sp is not None:
            m_xfrm = parse_xfrm(find(master_sp, "p:spPr"))
            xfrm = m_xfrm or xfrm
        fmt = _resolve_ph_format(info["type"], sp, master_sp, master_el,
                                 theme_colors, clr_map, font_scheme)
        name_el = find(sp, ".//p:nvSpPr/p:cNvPr")
        entry = {
            "name": name_el.get("name") if name_el is not None else None,
            "type": info["type"],
            "idx": info["idx"],
            "z_order": z,
            "position": _pos_dict(xfrm, slide_w, slide_h),
            "size": _size_dict(xfrm, slide_w, slide_h),
            "format_levels": {str(k): v for k, v in fmt.items()},
        }
        placeholders.append(entry)
    return placeholders


def _pos_dict(xfrm, slide_w, slide_h):
    if not xfrm or xfrm.get("x") is None:
        return None
    return {
        "x_in": emu_to_in(xfrm["x"]), "y_in": emu_to_in(xfrm["y"]),
        "x_pct": emu_to_pct(xfrm["x"], slide_w),
        "y_pct": emu_to_pct(xfrm["y"], slide_h),
    }


def _size_dict(xfrm, slide_w, slide_h):
    if not xfrm or xfrm.get("cx") is None:
        return None
    return {
        "width_in": emu_to_in(xfrm["cx"]), "height_in": emu_to_in(xfrm["cy"]),
        "width_pct": emu_to_pct(xfrm["cx"], slide_w),
        "height_pct": emu_to_pct(xfrm["cy"], slide_h),
    }


# ------------------------------------------------------------- static text

def extract_static_texts(tree_el, slide_w, slide_h, theme_colors, clr_map,
                         font_scheme) -> list[dict]:
    """Non-placeholder text shapes that are part of the layout's furniture
    (copyright lines, static captions). Returns positioned text records."""
    out = []
    if tree_el is None:
        return out
    for sp in findall(tree_el, "p:sp"):
        if _ph_info(sp) is not None:
            continue
        name_el = find(sp, ".//p:nvSpPr/p:cNvPr")
        if name_el is not None and name_el.get("hidden") == "1":
            continue
        tx_body = find(sp, "p:txBody")
        if tx_body is None:
            continue
        paragraphs = []
        for para in findall(tx_body, "a:p"):
            text = "".join(t.text or "" for t in para.iter(q("a:t"))).strip()
            if text:
                paragraphs.append(text)
        if not paragraphs:
            continue
        xfrm = parse_xfrm(find(sp, "p:spPr"))
        pos = _pos_dict(xfrm, slide_w, slide_h)
        size = _size_dict(xfrm, slide_w, slide_h)
        if pos is None or size is None:
            continue
        # formatting from the first run of the first paragraph
        first_p = find(tx_body, "a:p")
        rpr = find(first_p, "a:r/a:rPr")
        fmt = _rpr_props(rpr, theme_colors, clr_map, font_scheme)
        fmt.update({k: v for k, v in _ppr_props(
            find(first_p, "a:pPr"), theme_colors, clr_map).items()
            if k == "align"})
        out.append({
            "name": name_el.get("name") if name_el is not None else None,
            "paragraphs": paragraphs,
            "position": pos, "size": size,
            "format": fmt,
        })
    return out


# --------------------------------------------------------------- background

def extract_background(layout_el, master_el, theme_colors, clr_map,
                       fmt_scheme) -> tuple[dict, object | None]:
    """Returns (background_def, blip_element_or_None). The blip element is
    returned so the asset extractor can pull the image bytes via part rels.
    """
    for el, origin in ((layout_el, "layout"), (master_el, "master")):
        bg = find(el, ".//p:cSld/p:bg")
        if bg is None:
            continue
        bg_pr = find(bg, "p:bgPr")
        if bg_pr is not None:
            solid = find(bg_pr, "a:solidFill")
            if solid is not None:
                c = resolve_color(solid, theme_colors, clr_map)
                return ({"type": "solid", "hex": (c or {}).get("hex", "FFFFFF"),
                         "source": origin}, None)
            grad = find(bg_pr, "a:gradFill")
            if grad is not None:
                g = _summarize_gradient(grad, theme_colors, clr_map)
                g["source"] = origin
                return (g, None)
            blip_fill = find(bg_pr, "a:blipFill")
            if blip_fill is not None:
                blip = find(blip_fill, "a:blip")
                return ({"type": "image", "source": origin,
                         "asset_id": None}, (blip, origin))
        bg_ref = find(bg, "p:bgRef")
        if bg_ref is not None:
            idx = int(bg_ref.get("idx", 0))
            c = resolve_color(bg_ref, theme_colors, clr_map)
            fill = None
            if idx >= 1001 and fmt_scheme.get("bg_fills"):
                pool = fmt_scheme["bg_fills"]
                fill = pool[min(idx - 1001, len(pool) - 1)]
            elif 1 <= idx <= 999 and fmt_scheme.get("fills"):
                pool = fmt_scheme["fills"]
                fill = pool[min(idx - 1, len(pool) - 1)]
            if fill and fill.get("type") == "gradient":
                out = dict(fill)
                out["source"] = f"{origin}:bgRef"
                return (out, None)
            hex_val = (c or {}).get("hex") or (fill or {}).get("hex") or "FFFFFF"
            return ({"type": "solid", "hex": hex_val, "source": f"{origin}:bgRef"}, None)
    return ({"type": "solid", "hex": "FFFFFF", "source": "default"}, None)
