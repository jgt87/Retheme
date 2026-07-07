"""Unit conversion helpers. All positioning math derives from slide size in EMU."""

EMU_PER_INCH = 914400
EMU_PER_PT = 12700
PX_PER_INCH = 96  # CSS reference pixel


def emu_to_in(emu: int | None) -> float | None:
    if emu is None:
        return None
    return round(emu / EMU_PER_INCH, 4)


def emu_to_px(emu: int | None) -> float | None:
    if emu is None:
        return None
    return round(emu / EMU_PER_INCH * PX_PER_INCH, 2)


def emu_to_pct(emu: int | None, total_emu: int) -> float | None:
    """Fraction of a slide dimension (0.0-1.0)."""
    if emu is None or not total_emu:
        return None
    return round(emu / total_emu, 4)


def centipt_to_pt(sz: int | None) -> float | None:
    """OOXML font sizes are in hundredths of a point (sz="4000" -> 40pt)."""
    if sz is None:
        return None
    return sz / 100


def angle_60k_to_deg(val: int | None) -> float | None:
    """OOXML angles are in 60000ths of a degree."""
    if val is None:
        return None
    return round(val / 60000, 2)
