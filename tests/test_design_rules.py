"""Mechanical checks for the UI rules in DESIGN.md, so a stray value fails the
suite instead of slowly eroding the design system.

- Colors are defined once, in tokens.css. Anywhere else a hex literal is a
  bug (user/deck data colors are built at runtime as `#${hex}` and are fine).
- Font sizes come from the fixed type scale in tokens.css.
- Every status line and error box is announced to screen readers.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "pptx_template_tool" / "webapp" / "static"
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
PX_SIZE = re.compile(r"font(?:-size)?\s*:\s*(\d+(?:\.\d+)?)px")
TYPE_SCALE = {11, 12, 13, 14, 16, 20}


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


def _ui_files():
    return [STATIC / "index.html", STATIC / "app.css", STATIC / "app.js"]


def test_no_hex_colors_outside_tokens():
    offenders = []
    for path in _ui_files():
        for n, line in enumerate(_strip_comments(path.read_text(encoding="utf-8")).splitlines(), 1):
            if HEX.search(line):
                offenders.append(f"{path.name}:{n}: {line.strip()}")
    assert not offenders, "hex colors belong in tokens.css:\n" + "\n".join(offenders)


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
