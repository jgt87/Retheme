"""Mechanical checks for the UI rules in DESIGN.md, so a stray value fails the
suite instead of slowly eroding the design system.

- Colors are defined once, in tokens.css. Anywhere else a hex literal or a
  color function is a bug (user/deck data colors are built at runtime as
  `#${hex}` and are fine).
- Font sizes come from the fixed type scale in tokens.css.
- Spacing (margin, padding, gap) comes from the spacing tokens.
- Every custom property that is read is defined.
- Text and control edges meet their contrast minimums.
- Every status line and error box is announced to screen readers.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "pptx_template_tool" / "webapp" / "static"
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
COLOR_FN = re.compile(r"\b(?:rgba?|hsla?|oklch|oklab|color-mix)\s*\(")
PX_SIZE = re.compile(r"font(?:-size)?\s*:\s*(\d+(?:\.\d+)?)px")
SPACING_DECL = re.compile(r"(?<![\w-])(?:margin|padding|gap)(?:-[a-z]+)?\s*:\s*([^;}]+)")
TYPE_SCALE = {11, 12, 13, 14, 16, 20}
SPACING_SCALE = {4, 8, 12, 16, 24, 32}
# Hairline offsets that are not layout spacing (pill and code-chip padding).
SPACING_LITERALS = {0, 1, 2}


def _strip_comments(text: str) -> str:
    """Blank out comments but keep the line count, so failures name the line."""
    def blank(match):
        return "\n" * match.group(0).count("\n")
    text = re.sub(r"/\*.*?\*/", blank, text, flags=re.S)
    text = re.sub(r"<!--.*?-->", blank, text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


def _ui_files():
    return [STATIC / "index.html", STATIC / "app.css", STATIC / "app.js"]


def _tokens() -> dict[str, str]:
    text = _strip_comments((STATIC / "tokens.css").read_text(encoding="utf-8"))
    return {name: value.strip()
            for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", text)}


def test_no_hex_colors_outside_tokens():
    offenders = []
    for path in _ui_files():
        for n, line in enumerate(_strip_comments(path.read_text(encoding="utf-8")).splitlines(), 1):
            if HEX.search(line):
                offenders.append(f"{path.name}:{n}: {line.strip()}")
    assert not offenders, "hex colors belong in tokens.css:\n" + "\n".join(offenders)


def test_no_color_functions_outside_tokens():
    offenders = []
    for path in (STATIC / "index.html", STATIC / "app.css"):
        for n, line in enumerate(_strip_comments(path.read_text(encoding="utf-8")).splitlines(), 1):
            if COLOR_FN.search(line):
                offenders.append(f"{path.name}:{n}: {line.strip()}")
    assert not offenders, "color functions belong in tokens.css:\n" + "\n".join(offenders)


def test_font_sizes_on_the_type_scale():
    tokens = (STATIC / "tokens.css").read_text(encoding="utf-8")
    declared = {int(v) for v in re.findall(r"--fs-\w+:(\d+)px", tokens)}
    assert declared == TYPE_SCALE, f"tokens.css type scale drifted: {sorted(declared)}"
    offenders = []
    for path in _ui_files():
        for n, line in enumerate(_strip_comments(path.read_text(encoding="utf-8")).splitlines(), 1):
            for size in PX_SIZE.findall(line):
                if float(size) not in TYPE_SCALE:
                    offenders.append(f"{path.name}:{n}: {size}px")
    assert not offenders, "font size off the scale 11/12/13/14/16/20:\n" + "\n".join(offenders)


def test_spacing_on_the_spacing_scale():
    declared = {int(v) for v in re.findall(r"--sp-\w+:(\d+)px",
                                           (STATIC / "tokens.css").read_text(encoding="utf-8"))}
    assert declared == SPACING_SCALE, f"tokens.css spacing scale drifted: {sorted(declared)}"
    offenders = []
    css = _strip_comments((STATIC / "app.css").read_text(encoding="utf-8"))
    for n, line in enumerate(css.splitlines(), 1):
        for value in SPACING_DECL.findall(line):
            for px in re.findall(r"(-?\d+(?:\.\d+)?)px", value):
                if abs(float(px)) not in SPACING_LITERALS:
                    offenders.append(f"app.css:{n}: {px}px in '{value.strip()}'")
    assert not offenders, ("margin, padding and gap use the --sp-* tokens:\n"
                           + "\n".join(offenders))


def test_every_custom_property_read_is_defined():
    defined = set(_tokens())
    offenders = []
    for path in _ui_files():
        text = _strip_comments(path.read_text(encoding="utf-8"))
        for n, line in enumerate(text.splitlines(), 1):
            for name in re.findall(r"var\((--[\w-]+)\s*\)", line):
                if name not in defined:
                    offenders.append(f"{path.name}:{n}: {name}")
            for name in re.findall(r"cssVar\(\"(--[\w-]+)\"\)", line):
                if name not in defined:
                    offenders.append(f"{path.name}:{n}: {name}")
    assert not offenders, "undefined custom property:\n" + "\n".join(offenders)


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_token_contrast():
    t = _tokens()
    # (foreground, background, minimum): text 4.5:1, control edges 3:1
    pairs = [("--ink", "--surface", 4.5), ("--ink", "--bg", 4.5),
             ("--muted", "--surface", 4.5), ("--muted", "--bg", 4.5),
             ("--warn", "--surface", 4.5), ("--error-text", "--error-bg", 4.5),
             ("--on-accent", "--brand", 4.5), ("--brand", "--surface", 4.5),
             ("--stage-ink", "--stage-bg", 4.5),
             ("--line-strong", "--surface", 3.0), ("--line-strong", "--bg", 3.0)]
    offenders = [f"{fg} on {bg}: {_contrast(t[fg], t[bg]):.2f} < {minimum}"
                 for fg, bg, minimum in pairs if _contrast(t[fg], t[bg]) < minimum]
    assert not offenders, "contrast below the minimum:\n" + "\n".join(offenders)


def test_status_and_error_regions_are_announced():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for el_id in ("progress-step", "save-status", "apply-status",
                  "confirm-status", "preview-status"):
        assert re.search(rf'id="{el_id}"[^>]*role="status"', html), el_id
    for el_id in ("error-box", "apply-error"):
        assert re.search(rf'id="{el_id}"[^>]*role="alert"', html), el_id


def test_disabled_controls_use_not_allowed_cursor():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    for rule in re.findall(r"[^{}]*:disabled\s*\{[^}]*\}", css):
        if "cursor" in rule:
            assert "not-allowed" in rule, rule.strip()


def test_buttons_declare_their_type():
    html = _strip_comments((STATIC / "index.html").read_text(encoding="utf-8"))
    offenders = [tag for tag in re.findall(r"<button\b[^>]*>", html)
                 if 'type="button"' not in tag]
    assert not offenders, "buttons need type=\"button\":\n" + "\n".join(offenders)
