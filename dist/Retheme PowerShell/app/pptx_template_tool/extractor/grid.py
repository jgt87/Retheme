"""Derive consistent margins/gutters by comparing placeholder positions
across multiple layouts (spec §3.5)."""

from __future__ import annotations

from collections import Counter

from ..units import emu_to_in


def _mode_within(values: list[float], tolerance: float = 0.05):
    """Most common value after bucketing to `tolerance` inches."""
    if not values:
        return None
    buckets = Counter(round(v / tolerance) for v in values)
    bucket, count = buckets.most_common(1)[0]
    return round(bucket * tolerance, 3), count


def derive_grid(layouts: list[dict], slide_w_emu: int, slide_h_emu: int) -> dict:
    slide_w = emu_to_in(slide_w_emu)
    slide_h = emu_to_in(slide_h_emu)
    lefts, rights, tops, bottoms, title_baselines = [], [], [], [], []

    for layout in layouts:
        for ph in layout.get("placeholders", []):
            pos, size = ph.get("position"), ph.get("size")
            if not pos or not size:
                continue
            if ph["type"] in ("sldNum", "ftr", "dt"):
                continue  # footer strip shouldn't define content margins
            lefts.append(pos["x_in"])
            rights.append(slide_w - (pos["x_in"] + size["width_in"]))
            tops.append(pos["y_in"])
            bottoms.append(slide_h - (pos["y_in"] + size["height_in"]))
            if ph["type"] in ("title", "ctrTitle"):
                title_baselines.append(pos["y_in"] + size["height_in"])

    grid = {"slide_width_in": slide_w, "slide_height_in": slide_h}
    for key, values in (("margin_left_in", lefts), ("margin_right_in", rights),
                        ("margin_top_in", tops), ("margin_bottom_in", bottoms)):
        mode = _mode_within(values)
        if mode:
            value, count = mode
            grid[key] = value
            grid[key.replace("_in", "_consistency")] = round(count / len(values), 2)

    if title_baselines:
        baseline, count = _mode_within(title_baselines, tolerance=0.1)
        if count / len(title_baselines) >= 0.5:
            grid["title_baseline_in"] = baseline
            grid["title_baseline_consistency"] = round(count / len(title_baselines), 2)
    return grid
