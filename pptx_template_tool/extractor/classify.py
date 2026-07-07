"""Asset classification heuristics (spec §3.4). All classifications are
tentative and surfaced for human review; low-confidence ones are flagged."""

from __future__ import annotations


def classify_asset(asset: dict, slide_w_in: float, slide_h_in: float,
                   layout_purposes: dict[str, str]) -> tuple[str, str]:
    """Returns (type, confidence). asset must have position/size (in inches),
    owning_layouts (list of layout names), is_image (bool), z_order.
    """
    pos, size = asset.get("position"), asset.get("size")
    if not pos or not size:
        return ("decorative_shape", "low")

    slide_area = slide_w_in * slide_h_in
    area = (size["width_in"] or 0) * (size["height_in"] or 0)
    area_frac = area / slide_area if slide_area else 0
    n_layouts = len(asset.get("owning_layouts", []))
    # the template author's own shape name is a strong signal
    named_logo = "logo" in (asset.get("asset_id") or "").lower()

    cx = pos["x_in"] + size["width_in"] / 2
    cy = pos["y_in"] + size["height_in"] / 2
    in_corner = ((cx < slide_w_in * 0.25 or cx > slide_w_in * 0.75) and
                 (cy < slide_h_in * 0.25 or cy > slide_h_in * 0.75))

    if asset.get("is_image"):
        # full-bleed image -> background (high confidence when at the back)
        if area_frac >= 0.85:
            behind = asset.get("z_order", 99) <= 2
            return ("background_image", "high" if behind else "low")
        if named_logo and area_frac <= 0.1:
            return ("logo", "high")
        # small corner image repeated across layouts -> logo
        if area_frac <= 0.04 and in_corner:
            return ("logo", "high" if n_layouts >= 2 else "low")
        if area_frac <= 0.04 and n_layouts >= 3:
            return ("logo", "low")
        if area_frac <= 0.02:
            return ("icon", "low")
        return ("content_placeholder_image", "low")

    # vector shapes
    w, h = size["width_in"] or 0.001, size["height_in"] or 0.001
    aspect = max(w, h) / max(min(w, h), 0.001)
    if aspect >= 10:
        # a rule/divider line is decorative regardless of where it appears
        return ("decorative_shape", "high")
    if named_logo and area_frac <= 0.1:
        return ("logo", "high")
    if area_frac <= 0.04 and in_corner and n_layouts >= 2:
        return ("logo", "high")  # vector logos exist too (logotype shapes)
    on_section_headers = any(
        "Section" in layout_purposes.get(name, "")
        for name in asset.get("owning_layouts", []))
    if area_frac <= 0.02 and on_section_headers and n_layouts >= 1:
        return ("icon", "low")
    if area_frac >= 0.85 and asset.get("z_order", 99) <= 2:
        return ("background_image", "low")
    return ("decorative_shape", "high" if n_layouts >= 2 else "low")


def role_notes(asset: dict, slide_w_in: float, slide_h_in: float,
               total_layouts: int) -> str:
    pos, size = asset.get("position"), asset.get("size")
    if not pos or not size:
        return "position unknown (grouped/inherited transform)"
    cx = pos["x_in"] + size["width_in"] / 2
    cy = pos["y_in"] + size["height_in"] / 2
    horiz = "left" if cx < slide_w_in / 3 else ("right" if cx > 2 * slide_w_in / 3 else "center")
    vert = "top" if cy < slide_h_in / 3 else ("bottom" if cy > 2 * slide_h_in / 3 else "middle")
    owners = asset.get("owning_layouts", [])
    if len(owners) >= max(total_layouts - 1, 2) and total_layouts > 2:
        where = "all layouts" if len(owners) == total_layouts else \
            f"all layouts except {total_layouts - len(owners)}"
    elif len(owners) == 1:
        where = f'layout "{owners[0]}"'
    else:
        where = f"{len(owners)} layouts"
    return f"appears {vert}-{horiz} on {where}"
