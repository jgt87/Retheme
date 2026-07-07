"""Convert OOXML shape geometry (preset + custom) to standalone SVG so
decorative shapes scale cleanly in HTML.

Shapes that don't map cleanly are flagged `raster_fallback` (see spec §3.4);
without a rasterizer available we emit a bounding-box placeholder SVG and
mark the asset `needs_review` so the review UI surfaces it.
"""

from __future__ import annotations

import math

from lxml import etree

from ..ooxml import find, findall, resolve_color
from ..units import emu_to_px

# Presets we can emit natively. Anything else tries custGeom, then falls back.
_SIMPLE_PRESETS = {
    "rect", "roundRect", "ellipse", "line", "straightConnector1",
    "triangle", "rtTriangle", "diamond", "parallelogram", "trapezoid",
    "pentagon", "hexagon", "chevron", "homePlate", "rightArrow", "leftArrow",
    "upArrow", "downArrow", "octagon", "plus", "donut",
}


def _style_ref_color(sp, ref_tag: str, theme_colors, clr_map) -> dict | None:
    """Resolve a p:style reference (a:fillRef / a:lnRef). idx=0 means none."""
    ref = find(sp, f"p:style/{ref_tag}")
    if ref is None or int(ref.get("idx", 0)) == 0:
        return None
    return resolve_color(ref, theme_colors, clr_map)


def _fill_attrs(sp_pr, theme_colors, clr_map, defs: list, shape_id: str) -> dict:
    solid = find(sp_pr, "a:solidFill")
    if solid is not None:
        c = resolve_color(solid, theme_colors, clr_map)
        if c:
            attrs = {"fill": f"#{c['hex']}"}
            if c["alpha"] < 1:
                attrs["fill-opacity"] = str(c["alpha"])
            return attrs
    grad = find(sp_pr, "a:gradFill")
    if grad is not None:
        stops = []
        for gs in findall(grad, "a:gsLst/a:gs"):
            c = resolve_color(gs, theme_colors, clr_map)
            if c:
                stops.append((int(gs.get("pos", 0)) / 100000, c))
        stops.sort(key=lambda s: s[0])
        lin = find(grad, "a:lin")
        ang = int(lin.get("ang", 0)) / 60000 if lin is not None else 0
        rad = math.radians(ang)
        x2, y2 = (math.cos(rad) + 1) / 2, (math.sin(rad) + 1) / 2
        x1, y1 = 1 - x2, 1 - y2
        grad_id = f"g{shape_id}"
        stop_parts = []
        for p, c in stops:
            opacity = f' stop-opacity="{c["alpha"]}"' if c["alpha"] < 1 else ""
            stop_parts.append(
                f'<stop offset="{p:.3f}" stop-color="#{c["hex"]}"{opacity}/>')
        stop_xml = "".join(stop_parts)
        defs.append(
            f'<linearGradient id="{grad_id}" x1="{x1:.3f}" y1="{y1:.3f}" '
            f'x2="{x2:.3f}" y2="{y2:.3f}">{stop_xml}</linearGradient>')
        return {"fill": f"url(#{grad_id})"}
    if find(sp_pr, "a:noFill") is not None:
        return {"fill": "none"}
    return {}  # no explicit fill: caller may fall back to p:style fillRef


def _stroke_attrs(sp_pr, theme_colors, clr_map, ref_color=None) -> dict:
    ln = find(sp_pr, "a:ln")
    if ln is None:
        if ref_color:  # line style comes from p:style lnRef
            return {"stroke": f"#{ref_color['hex']}", "stroke-width": "1"}
        return {}
    if find(ln, "a:noFill") is not None:
        return {}
    c = resolve_color(find(ln, "a:solidFill"), theme_colors, clr_map) or ref_color
    if c is None:
        return {}
    width = emu_to_px(int(ln.get("w", 9525))) or 1
    attrs = {"stroke": f"#{c['hex']}", "stroke-width": f"{width:g}"}
    dash = find(ln, "a:prstDash")
    if dash is not None and dash.get("val") not in (None, "solid"):
        attrs["stroke-dasharray"] = {"dash": "8 4", "dot": "2 3",
                                     "lgDash": "12 4"}.get(dash.get("val"), "6 3")
    if c["alpha"] < 1:
        attrs["stroke-opacity"] = str(c["alpha"])
    return attrs


def _preset_path(preset: str, w: float, h: float, adjustments: dict) -> str | None:
    """SVG path 'd' for a preset geometry in a w×h px box."""
    a = adjustments
    if preset == "rect":
        return f"M0 0 H{w} V{h} H0 Z"
    if preset == "roundRect":
        r = min(w, h) * a.get("adj", 16667) / 100000
        return (f"M{r} 0 H{w-r} Q{w} 0 {w} {r} V{h-r} Q{w} {h} {w-r} {h} "
                f"H{r} Q0 {h} 0 {h-r} V{r} Q0 0 {r} 0 Z")
    if preset == "ellipse":
        rx, ry = w / 2, h / 2
        return (f"M0 {ry} A{rx} {ry} 0 1 0 {w} {ry} "
                f"A{rx} {ry} 0 1 0 0 {ry} Z")
    if preset in ("line", "straightConnector1"):
        return f"M0 0 L{w} {h}"
    if preset == "triangle":
        return f"M{w/2} 0 L{w} {h} L0 {h} Z"
    if preset == "rtTriangle":
        return f"M0 0 L{w} {h} L0 {h} Z"
    if preset == "diamond":
        return f"M{w/2} 0 L{w} {h/2} L{w/2} {h} L0 {h/2} Z"
    if preset == "parallelogram":
        off = w * a.get("adj", 25000) / 100000
        return f"M{off} 0 H{w} L{w-off} {h} H0 Z"
    if preset == "trapezoid":
        off = w * a.get("adj", 25000) / 100000
        return f"M{off} 0 H{w-off} L{w} {h} H0 Z"
    if preset == "pentagon":
        return (f"M{w/2} 0 L{w} {h*0.38} L{w*0.81} {h} L{w*0.19} {h} "
                f"L0 {h*0.38} Z")
    if preset == "hexagon":
        off = min(w, h) * a.get("adj", 25000) / 100000
        return f"M{off} 0 H{w-off} L{w} {h/2} L{w-off} {h} H{off} L0 {h/2} Z"
    if preset in ("chevron", "homePlate"):
        off = min(w, h) * a.get("adj", 50000 if preset == "chevron" else 50000) / 100000
        start = off if preset == "chevron" else 0
        return (f"M{start if preset=='chevron' else 0} {h/2} L0 0 H{w-off} "
                f"L{w} {h/2} L{w-off} {h} H0 Z") if preset == "chevron" else \
               (f"M0 0 H{w-off} L{w} {h/2} L{w-off} {h} H0 Z")
    if preset == "rightArrow":
        head = w * a.get("adj2", 50000) / 100000
        body = h * (1 - a.get("adj1", 50000) / 100000) / 2
        return (f"M0 {body} H{w-head} V0 L{w} {h/2} L{w-head} {h} "
                f"V{h-body} H0 Z")
    if preset == "leftArrow":
        head = w * a.get("adj2", 50000) / 100000
        body = h * (1 - a.get("adj1", 50000) / 100000) / 2
        return (f"M{w} {body} H{head} V0 L0 {h/2} L{head} {h} "
                f"V{h-body} H{w} Z")
    if preset == "upArrow":
        head = h * a.get("adj2", 50000) / 100000
        body = w * (1 - a.get("adj1", 50000) / 100000) / 2
        return (f"M{body} {h} V{head} H0 L{w/2} 0 L{w} {head} "
                f"H{w-body} V{h} Z")
    if preset == "downArrow":
        head = h * a.get("adj2", 50000) / 100000
        body = w * (1 - a.get("adj1", 50000) / 100000) / 2
        return (f"M{body} 0 V{h-head} H0 L{w/2} {h} L{w} {h-head} "
                f"H{w-body} V0 Z")
    if preset == "octagon":
        off = min(w, h) * a.get("adj", 29289) / 100000
        return (f"M{off} 0 H{w-off} L{w} {off} V{h-off} L{w-off} {h} "
                f"H{off} L0 {h-off} V{off} Z")
    if preset == "plus":
        off = min(w, h) * a.get("adj", 25000) / 100000
        return (f"M{off} 0 H{w-off} V{off} H{w} V{h-off} H{w-off} V{h} "
                f"H{off} V{h-off} H0 V{off} H{off} Z")
    if preset == "donut":
        rx, ry = w / 2, h / 2
        t = min(w, h) * a.get("adj", 25000) / 100000
        return (f"M0 {ry} A{rx} {ry} 0 1 0 {w} {ry} A{rx} {ry} 0 1 0 0 {ry} Z "
                f"M{t} {ry} A{rx-t} {ry-t} 0 1 1 {w-t} {ry} "
                f"A{rx-t} {ry-t} 0 1 1 {t} {ry} Z")
    return None


def _parse_adjustments(prst_geom) -> dict:
    adj = {}
    for gd in findall(prst_geom, "a:avLst/a:gd"):
        fmla = gd.get("fmla", "")
        if fmla.startswith("val "):
            try:
                adj[gd.get("name")] = int(fmla[4:])
            except ValueError:
                pass
    return adj


def _cust_geom_path(cust_geom, w_px: float, h_px: float) -> str | None:
    """Convert a:custGeom a:pathLst to an SVG path. Returns None if the
    geometry uses features we can't map (formula-driven guides in points)."""
    parts = []
    for path in findall(cust_geom, "a:pathLst/a:path"):
        pw = int(path.get("w", 0)) or None
        ph = int(path.get("h", 0)) or None
        sx = w_px / pw if pw else 1.0
        sy = h_px / ph if ph else 1.0

        def pt(el):
            x, y = el.get("x"), el.get("y")
            if x is None or y is None or not x.lstrip("-").isdigit() or not y.lstrip("-").isdigit():
                raise ValueError("non-numeric guide reference")
            return int(x) * sx, int(y) * sy

        cur = None
        try:
            for cmd in path:
                tag = etree.QName(cmd).localname
                if tag == "moveTo":
                    cur = pt(find(cmd, "a:pt"))
                    parts.append(f"M{cur[0]:.2f} {cur[1]:.2f}")
                elif tag == "lnTo":
                    cur = pt(find(cmd, "a:pt"))
                    parts.append(f"L{cur[0]:.2f} {cur[1]:.2f}")
                elif tag == "cubicBezTo":
                    pts = [pt(p) for p in findall(cmd, "a:pt")]
                    parts.append("C" + " ".join(f"{x:.2f} {y:.2f}" for x, y in pts))
                    cur = pts[-1]
                elif tag == "quadBezTo":
                    pts = [pt(p) for p in findall(cmd, "a:pt")]
                    parts.append("Q" + " ".join(f"{x:.2f} {y:.2f}" for x, y in pts))
                    cur = pts[-1]
                elif tag == "arcTo":
                    if cur is None:
                        raise ValueError("arcTo without current point")
                    wr = int(cmd.get("wR")) * sx
                    hr = int(cmd.get("hR")) * sy
                    st = int(cmd.get("stAng")) / 60000
                    sw = int(cmd.get("swAng")) / 60000
                    # center from start point + start angle
                    st_r, end_r = math.radians(st), math.radians(st + sw)
                    cx = cur[0] - wr * math.cos(st_r)
                    cy = cur[1] - hr * math.sin(st_r)
                    end = (cx + wr * math.cos(end_r), cy + hr * math.sin(end_r))
                    large = 1 if abs(sw) > 180 else 0
                    sweep = 1 if sw > 0 else 0
                    parts.append(f"A{wr:.2f} {hr:.2f} 0 {large} {sweep} "
                                 f"{end[0]:.2f} {end[1]:.2f}")
                    cur = end
                elif tag == "close":
                    parts.append("Z")
                else:
                    raise ValueError(f"unsupported path command {tag}")
        except (ValueError, TypeError, AttributeError):
            return None
    return " ".join(parts) if parts else None


def shape_to_svg(sp, theme_colors, clr_map, w_emu: int, h_emu: int,
                 shape_id: str) -> tuple[str | None, str]:
    """Returns (svg_text, source_format). source_format is 'vector' on
    success or 'raster_fallback' when we emit only a placeholder."""
    sp_pr = find(sp, "p:spPr")
    w = max(emu_to_px(w_emu) or 1, 1)
    h = max(emu_to_px(h_emu) or 1, 1)

    d = None
    prst = find(sp_pr, "a:prstGeom")
    cust = find(sp_pr, "a:custGeom")
    if prst is not None:
        name = prst.get("prst")
        if name in _SIMPLE_PRESETS:
            d = _preset_path(name, w, h, _parse_adjustments(prst))
    elif cust is not None:
        d = _cust_geom_path(cust, w, h)

    defs: list[str] = []
    fill = _fill_attrs(sp_pr, theme_colors, clr_map, defs, shape_id)
    if not fill:  # fall back to shape style reference, else no fill
        ref = _style_ref_color(sp, "a:fillRef", theme_colors, clr_map)
        fill = {"fill": f"#{ref['hex']}"} if ref else {"fill": "none"}
    ln_ref = _style_ref_color(sp, "a:lnRef", theme_colors, clr_map)
    stroke = _stroke_attrs(sp_pr, theme_colors, clr_map, ref_color=ln_ref)

    # nothing would be painted: not a visual asset
    if fill.get("fill") == "none" and "stroke" not in stroke:
        return None, "invisible"

    if d is None:
        # placeholder bounding box, flagged for review
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:g}" height="{h:g}" '
               f'viewBox="0 0 {w:g} {h:g}"><rect width="{w:g}" height="{h:g}" '
               f'fill="{fill.get("fill", "#CCCCCC")}" fill-opacity="0.4" '
               f'stroke="#FF00AA" stroke-dasharray="4 3"/></svg>')
        return svg, "raster_fallback"

    attrs = {**fill, **stroke}
    attr_str = " ".join(f'{k}="{v}"' for k, v in attrs.items())
    defs_str = f"<defs>{''.join(defs)}</defs>" if defs else ""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:g}" height="{h:g}" '
           f'viewBox="0 0 {w:g} {h:g}">{defs_str}<path d="{d}" {attr_str}/></svg>')
    return svg, "vector"
