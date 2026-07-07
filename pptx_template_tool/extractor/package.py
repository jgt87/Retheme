"""Template package writer.

`template.json` is the single source of truth. `template.md` is always
regenerated from the JSON (including after review-UI corrections), which
guarantees the two can never diverge (spec §3.6).
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path


def write_package(package_dir: Path, manifest: dict) -> None:
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "template.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (package_dir / "template.md").write_text(
        render_markdown(manifest), encoding="utf-8")


def zip_package(package_dir: Path, zip_path: Path) -> Path:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(package_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(package_dir))
    return zip_path


# ------------------------------------------------------------- markdown

def _fmt_pos(asset: dict) -> str:
    pos, size = asset.get("position"), asset.get("size")
    if not pos or not size:
        return "—"
    return (f'{pos["x_in"]:.2f}″, {pos["y_in"]:.2f}″ '
            f'({pos["x_pct"]*100:.1f}%, {pos["y_pct"]*100:.1f}%)')


def _fmt_size(asset: dict) -> str:
    size = asset.get("size")
    if not size:
        return "—"
    return f'{size["width_in"]:.2f}″ × {size["height_in"]:.2f}″'


def render_markdown(m: dict) -> str:
    lines: list[str] = []
    add = lines.append
    geo = m["slide_geometry"]
    grid = m.get("grid", {})

    add(f'# {m.get("template_name", "Template")} — Template Spec\n')

    add("## Slide Geometry\n")
    add(f'- Dimensions: {geo["width_in"]}″ × {geo["height_in"]}″ '
        f'({geo["aspect_ratio"]})')
    margins = [grid.get(k) for k in ("margin_left_in", "margin_top_in",
                                     "margin_right_in", "margin_bottom_in")]
    if any(v is not None for v in margins):
        add(f'- Safe margins (derived across layouts): left {margins[0]}″, '
            f'top {margins[1]}″, right {margins[2]}″, bottom {margins[3]}″')
    if grid.get("title_baseline_in"):
        add(f'- Title baseline: {grid["title_baseline_in"]}″ from top '
            f'(consistent on {grid.get("title_baseline_consistency", 0)*100:.0f}% of layouts)')
    add("")

    add("## Color Palette\n")
    add("| Hex | Theme slot | Semantic role | Observed usage |")
    add("|---|---|---|---|")
    for c in m.get("colors", []):
        usage = ", ".join(f"{k}×{v}" for k, v in sorted(
            c.get("usage", {}).items(), key=lambda kv: -kv[1])) or "unused"
        add(f'| `#{c["hex"]}` | {c["theme_slot"]} | **{c["role"]}** | {usage} |')
    add("")

    add("## Typography\n")
    fonts = m.get("fonts", {})
    add(f'- Heading font (major): **{fonts.get("heading", "?")}**')
    add(f'- Body font (minor): **{fonts.get("body", "?")}**\n')
    add("| Text role | Font | Size | Weight | Color |")
    add("|---|---|---|---|---|")
    seen_roles = set()
    for layout in m.get("layouts", []):
        for ph in layout.get("placeholders", []):
            lvl1 = ph.get("format_levels", {}).get("1", {})
            role = ph["type"]
            key = (role, lvl1.get("font"), lvl1.get("size_pt"))
            if key in seen_roles or not lvl1:
                continue
            seen_roles.add(key)
            add(f'| {role} | {lvl1.get("font", "—")} | '
                f'{lvl1.get("size_pt", "—")}pt | '
                f'{"bold" if lvl1.get("bold") else "regular"} | '
                f'{"#" + lvl1["color"] if lvl1.get("color") else "—"} |')
    add("")

    add("## Assets\n")
    add("| asset_id | type | format | file | owning layout(s) | position | size | z |")
    add("|---|---|---|---|---|---|---|---|")
    for a in m.get("assets", []):
        owners = a.get("owning_layouts", [])
        owner_str = "all" if a.get("owning_layout") == "all" else \
            ", ".join(owners[:3]) + (f" (+{len(owners)-3})" if len(owners) > 3 else "")
        flag = " ⚠️" if a.get("needs_review") else ""
        file_str = f'`{a["file_path"]}`' if a.get("file_path") else "— (background mask)"
        add(f'| `{a["asset_id"]}`{flag} | {a["type"]} | {a["source_format"]} | '
            f'{file_str} | {owner_str} | {_fmt_pos(a)} | {_fmt_size(a)} '
            f'| {a.get("z_order", "—")} |')
    add("")
    logos = [a for a in m.get("assets", []) if a["type"] == "logo"]
    if logos:
        add("### Logo usage rules\n")
        for logo in logos:
            add(f'- `{logo["asset_id"]}`: {logo.get("role_notes", "")}. '
                f'Keep at extracted size ({_fmt_size(logo)}) and position; '
                f'do not place content within its bounding box.')
        add("")

    add("## Layout Catalog\n")
    for layout in m.get("layouts", []):
        add(f'### Layout: "{layout["name"]}"\n')
        add(f'- **Purpose**: {layout.get("purpose", "?")}')
        bg = layout.get("background", {})
        if bg.get("type") == "solid":
            add(f'- **Background**: solid `#{bg.get("hex", "FFFFFF")}`')
        elif bg.get("type") == "gradient":
            stops = " → ".join(f'#{s["hex"]}' for s in bg.get("stops", []))
            add(f'- **Background**: gradient {stops} at {bg.get("angle_deg", 0)}°')
        elif bg.get("type") == "image":
            add(f'- **Background**: image (`{bg.get("asset_id", "?")}`)')
        if layout.get("static_assets"):
            add(f'- **Static assets**: ' +
                ", ".join(f'`{a}`' for a in layout["static_assets"]))
        phs = layout.get("placeholders", [])
        if phs:
            add("- **Placeholder map**:\n")
            add("| type | position | size | font | size | color | align |")
            add("|---|---|---|---|---|---|---|")
            for ph in phs:
                lvl1 = ph.get("format_levels", {}).get("1", {})
                add(f'| {ph["type"]} | {_fmt_pos(ph)} | {_fmt_size(ph)} | '
                    f'{lvl1.get("font", "—")} | {lvl1.get("size_pt", "—")}pt | '
                    f'{"#" + lvl1["color"] if lvl1.get("color") else "—"} | '
                    f'{lvl1.get("align", "—")} |')
        add("")

    add("## Motifs & Recurring Decorative Elements\n")
    recurring = [a for a in m.get("assets", [])
                 if len(a.get("owning_layouts", [])) >= 2
                 and a["type"] in ("decorative_shape", "icon", "logo")]
    if recurring:
        for a in recurring:
            add(f'- `{a["asset_id"]}` ({a["type"]}): {a.get("role_notes", "")}')
    else:
        add("- No decorative element recurs across multiple layouts.")
    add("")

    add("## Do's and Don'ts\n")
    add("Derived from what is/isn't present in the template:\n")
    fonts_used = {fonts.get("heading"), fonts.get("body")} - {None}
    add(f'- **Do** use only the template fonts: {", ".join(sorted(fonts_used))}.')
    primary = [c for c in m.get("colors", []) if c["role"] == "primary"]
    if primary:
        add(f'- **Do** use `#{primary[0]["hex"]}` as the dominant brand color.')
    grad_layouts = [l["name"] for l in m.get("layouts", [])
                    if l.get("background", {}).get("type") == "gradient"]
    if grad_layouts:
        add(f"- **Do** reserve gradient backgrounds for: {', '.join(grad_layouts[:4])}.")
    else:
        add("- **Don't** introduce gradient backgrounds — the template uses none.")
    if not any(a["type"] == "background_image" for a in m.get("assets", [])):
        add("- **Don't** use full-bleed photo backgrounds — the template has none.")
    if logos:
        add("- **Don't** recolor, stretch, or reposition the logo.")
    add("- **Don't** invent new layout structures; use the Layout Catalog above.")
    add("")

    if m.get("extraction_notes"):
        add("## Extraction Notes\n")
        for note in m["extraction_notes"]:
            add(f"- {note}")
        add("")

    return "\n".join(lines)
