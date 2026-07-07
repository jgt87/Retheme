"""Asset extraction: embedded images, background image fills, and decorative
vector shapes — each with exact position/size/z-order/crop metadata so it can
be placed back identically during HTML generation."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from lxml import etree

from ..ooxml import NS, find, parse_xfrm, compose_group_transform
from ..units import emu_to_in, emu_to_pct
from .layouts import _pos_dict, _size_dict
from .svg_convert import shape_to_svg

_EXT_BY_CT = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
    "image/svg+xml": ".svg", "image/x-emf": ".emf", "image/emf": ".emf",
    "image/x-wmf": ".wmf", "image/tiff": ".tiff", "image/bmp": ".bmp",
}
_RASTER_OK = {".png", ".jpg", ".gif", ".bmp", ".tiff"}


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "asset"


class AssetCollector:
    """Accumulates assets across masters/layouts, deduplicating identical
    images/shapes that recur (same content + geometry -> one asset whose
    owning_layouts grows)."""

    def __init__(self, assets_dir: Path, slide_w: int, slide_h: int):
        self.assets_dir = assets_dir
        self.slide_w, self.slide_h = slide_w, slide_h
        self.assets: dict[str, dict] = {}      # asset_id -> record
        self._by_key: dict[tuple, str] = {}    # dedupe key -> asset_id
        self._file_by_hash: dict[str, str] = {}  # content hash -> file name
        self._counter = 0

    # ------------------------------------------------------------ helpers

    def _new_id(self, base: str) -> str:
        base = _slug(base)
        candidate = base
        n = 2
        while candidate in self.assets:
            candidate = f"{base}-{n}"
            n += 1
        return candidate

    def _save_bytes(self, data: bytes, base: str, ext: str) -> str:
        digest = hashlib.sha1(data).hexdigest()[:12]
        if digest in self._file_by_hash:
            return self._file_by_hash[digest]
        fname = f"{_slug(base)}-{digest[:6]}{ext}"
        (self.assets_dir / fname).write_bytes(data)
        self._file_by_hash[digest] = fname
        return fname

    def _register(self, key: tuple, record: dict, layout_name: str) -> str:
        if key in self._by_key:
            asset_id = self._by_key[key]
            owners = self.assets[asset_id]["owning_layouts"]
            if layout_name not in owners:
                owners.append(layout_name)
            return asset_id
        asset_id = self._new_id(record["name_hint"])
        record["asset_id"] = asset_id
        record["owning_layouts"] = [layout_name]
        self.assets[asset_id] = record
        self._by_key[key] = asset_id
        return asset_id

    def _geometry(self, xfrm) -> tuple[dict | None, dict | None, dict | None]:
        pos = _pos_dict(xfrm, self.slide_w, self.slide_h)
        size = _size_dict(xfrm, self.slide_w, self.slide_h)
        crop = None
        if xfrm and (xfrm.get("rot") or xfrm.get("flipH") or xfrm.get("flipV")):
            crop = {"rotation_deg": round(xfrm.get("rot", 0) / 60000, 2),
                    "flip_h": xfrm.get("flipH", False),
                    "flip_v": xfrm.get("flipV", False)}
        return pos, size, crop

    # ------------------------------------------------------------ pictures

    def _blip_bytes(self, blip, part) -> tuple[bytes, str] | None:
        """Resolve an a:blip to (bytes, extension), preferring embedded
        native SVG when present (modern PowerPoint)."""
        r_id = None
        svg_blip = find(blip, "a:extLst/a:ext/asvg:svgBlip")
        if svg_blip is not None:
            r_id = svg_blip.get(f"{{{NS['r']}}}embed")
        if r_id is None:
            r_id = blip.get(f"{{{NS['r']}}}embed")
        if r_id is None:
            return None
        try:
            image_part = part.related_part(r_id)
        except KeyError:
            return None
        ext = _EXT_BY_CT.get(image_part.content_type,
                             Path(str(image_part.partname)).suffix or ".bin")
        return image_part.blob, ext

    def _register_image(self, data: bytes, ext: str, name_hint: str,
                        xfrm: dict | None, src_rect, layout_name: str,
                        z_order: int) -> str:
        pos, size, crop = self._geometry(xfrm)
        if src_rect is not None:
            crop = crop or {}
            crop["crop_rect"] = {k: int(src_rect.get(k, 0)) / 100000
                                 for k in ("l", "t", "r", "b")}
        digest = hashlib.sha1(data).hexdigest()[:12]
        fname = self._save_bytes(data, name_hint, ext)
        if ext == ".svg":
            source_format = "vector"
        elif ext in _RASTER_OK:
            source_format = "raster"
        else:
            source_format = "raster_fallback"  # emf/wmf etc: needs review

        key = ("img", digest,
               round(pos["x_in"], 2) if pos else None,
               round(pos["y_in"], 2) if pos else None,
               round(size["width_in"], 2) if size else None)
        record = {
            "name_hint": name_hint,
            "type": None,  # classified later
            "is_image": True,
            "source_format": source_format,
            "file_path": f"assets/{fname}",
            "position": pos, "size": size, "z_order": z_order, "crop": crop,
            "needs_review": source_format == "raster_fallback",
        }
        return self._register(key, record, layout_name)

    def add_picture(self, pic, part, layout_name: str, z_order: int,
                    group_xfrm: dict | None = None) -> str | None:
        # the fill wrapper is p:blipFill on p:pic (PresentationML ns), so
        # search for the DrawingML a:blip itself, not its parent
        blip = find(pic, ".//a:blip")
        if blip is None:
            return None
        resolved = self._blip_bytes(blip, part)
        if resolved is None:
            return None
        data, ext = resolved

        name_el = find(pic, ".//p:nvPicPr/p:cNvPr")
        name_hint = (name_el.get("name") if name_el is not None else "") or "image"

        xfrm = parse_xfrm(find(pic, "p:spPr"))
        if xfrm and group_xfrm:
            xfrm = compose_group_transform(xfrm, group_xfrm)
        src_rect = find(pic, ".//a:srcRect")
        return self._register_image(data, ext, name_hint, xfrm, src_rect,
                                    layout_name, z_order)

    # ------------------------------------------------------- vector shapes

    def add_shape(self, sp, part, layout_name: str, z_order: int,
                  theme_colors, clr_map,
                  group_xfrm: dict | None = None) -> str | None:
        sp_pr = find(sp, "p:spPr")
        if sp_pr is None:
            return None
        xfrm = parse_xfrm(sp_pr)
        # lines may legitimately have zero width (vertical) or height
        # (horizontal); reject only shapes with no extent at all
        if xfrm is None or xfrm.get("cx") is None or xfrm.get("cy") is None \
                or (xfrm["cx"] == 0 and xfrm["cy"] == 0):
            return None
        if group_xfrm:
            xfrm = compose_group_transform(xfrm, group_xfrm)

        # useBgFill shapes are "painted with the slide background" — used to
        # mask master elements (e.g. hide the logo on title slides)
        if sp.get("useBgFill") == "1":
            pos, size, crop = self._geometry(xfrm)
            name_el = find(sp, ".//p:nvSpPr/p:cNvPr")
            name_hint = (name_el.get("name")
                         if name_el is not None else "") or "bg-mask"
            key = ("mask",
                   round(pos["x_in"], 2) if pos else None,
                   round(pos["y_in"], 2) if pos else None,
                   round(size["width_in"], 2) if size else None)
            record = {
                "name_hint": name_hint,
                "type": "decorative_shape",
                "is_image": False,
                "source_format": "background_mask",
                "use_bg_fill": True,
                "file_path": None,
                "position": pos, "size": size, "z_order": z_order,
                "crop": crop, "needs_review": False,
            }
            return self._register(key, record, layout_name)

        # image-filled shape (a common way to build backgrounds/photos):
        # extract the fill image as an image asset at the shape's geometry
        blip_fill = find(sp_pr, "a:blipFill")
        if blip_fill is not None:
            blip = find(blip_fill, "a:blip")
            resolved = self._blip_bytes(blip, part) if blip is not None else None
            if resolved is not None:
                data, ext = resolved
                name_el = find(sp, ".//p:nvSpPr/p:cNvPr")
                name_hint = (name_el.get("name")
                             if name_el is not None else "") or "image-fill"
                return self._register_image(
                    data, ext, name_hint, xfrm,
                    find(blip_fill, "a:srcRect"), layout_name, z_order)

        has_geom = (find(sp_pr, "a:prstGeom") is not None or
                    find(sp_pr, "a:custGeom") is not None)
        has_paint = (find(sp_pr, "a:solidFill") is not None or
                     find(sp_pr, "a:gradFill") is not None or
                     find(sp_pr, "a:ln") is not None or
                     find(sp, "p:style") is not None)
        if not has_geom or not has_paint:
            return None  # invisible/utility shape, not a visual asset
        # skip authoring guides sitting (mostly) outside the slide canvas;
        # a zero dimension (flat line) counts as fully visible on that axis
        x, y = xfrm.get("x") or 0, xfrm.get("y") or 0
        cx, cy = xfrm.get("cx") or 0, xfrm.get("cy") or 0
        if x + cx < 0 or x > self.slide_w or y + cy < 0 or y > self.slide_h:
            return None
        frac_x = (min(x + cx, self.slide_w) - max(x, 0)) / cx if cx else 1.0
        frac_y = (min(y + cy, self.slide_h) - max(y, 0)) / cy if cy else 1.0
        if frac_x * frac_y < 0.4:
            return None
        pos, size, crop = self._geometry(xfrm)

        name_el = find(sp, ".//p:nvSpPr/p:cNvPr")
        if name_el is None:
            name_el = find(sp, ".//p:nvCxnSpPr/p:cNvPr")
        name_hint = (name_el.get("name") if name_el is not None else "") or "shape"

        self._counter += 1
        svg_text, source_format = shape_to_svg(
            sp, theme_colors, clr_map, xfrm["cx"], xfrm["cy"], str(self._counter))
        if svg_text is None:
            return None
        data = svg_text.encode("utf-8")
        digest = hashlib.sha1(data).hexdigest()[:12]
        fname = self._save_bytes(data, name_hint, ".svg")

        key = ("shape", digest,
               round(pos["x_in"], 2) if pos else None,
               round(pos["y_in"], 2) if pos else None)
        record = {
            "name_hint": name_hint,
            "type": None,
            "is_image": False,
            "source_format": source_format,
            "file_path": f"assets/{fname}",
            "position": pos, "size": size, "z_order": z_order, "crop": crop,
            "needs_review": source_format == "raster_fallback",
        }
        return self._register(key, record, layout_name)

    # --------------------------------------------------------- backgrounds

    def add_background_image(self, blip, part, layout_name: str) -> str | None:
        r_id = blip.get(f"{{{NS['r']}}}embed")
        if r_id is None:
            return None
        try:
            image_part = part.related_part(r_id)
        except KeyError:
            return None
        data = image_part.blob
        ext = _EXT_BY_CT.get(image_part.content_type, ".bin")
        digest = hashlib.sha1(data).hexdigest()[:12]
        fname = self._save_bytes(data, f"bg-{layout_name}", ext)
        key = ("bg", digest)
        record = {
            "name_hint": f"bg-{layout_name}",
            "type": "background_image",
            "is_image": True,
            "source_format": "raster" if ext in _RASTER_OK else "raster_fallback",
            "file_path": f"assets/{fname}",
            "position": {"x_in": 0, "y_in": 0, "x_pct": 0, "y_pct": 0},
            "size": {"width_in": emu_to_in(self.slide_w),
                     "height_in": emu_to_in(self.slide_h),
                     "width_pct": 1.0, "height_pct": 1.0},
            "z_order": 0, "crop": None,
            "needs_review": ext not in _RASTER_OK,
        }
        return self._register(key, record, layout_name)

    # ------------------------------------------------------------- walking

    def walk_tree(self, sp_tree, part, layout_name: str, theme_colors,
                  clr_map) -> list[str]:
        """Walk a cSld/spTree, returning asset ids found (placeholders are
        skipped — they're captured by the layout extractor)."""
        found: list[str] = []
        z = 0

        def visit(container, group_xfrm):
            nonlocal z
            for child in container:
                tag = etree.QName(child).localname
                if tag not in ("sp", "pic", "grpSp", "cxnSp"):
                    continue
                # PowerPoint never renders shapes marked hidden (e.g. master
                # helper grids) — skip them, including entire hidden groups
                cnvpr = child.find(f".//{{{NS['p']}}}cNvPr")
                if cnvpr is not None and cnvpr.get("hidden") == "1":
                    continue
                z += 1
                if tag == "pic":
                    aid = self.add_picture(child, part, layout_name, z, group_xfrm)
                    if aid:
                        found.append(aid)
                elif tag in ("sp", "cxnSp"):
                    if tag == "sp" and find(child, ".//p:nvSpPr/p:nvPr/p:ph") is not None:
                        continue  # placeholder
                    aid = self.add_shape(child, part, layout_name, z,
                                         theme_colors, clr_map, group_xfrm)
                    if aid:
                        found.append(aid)
                elif tag == "grpSp":
                    g_xfrm = parse_xfrm(find(child, "p:grpSpPr"))
                    if group_xfrm and g_xfrm:
                        g_xfrm = compose_group_transform(g_xfrm, group_xfrm)
                    visit(child, g_xfrm)
        visit(sp_tree, None)
        return found
