"""Color harmonies around a Pantone anchor, for proposing a theme's other hues.

Two sources, best first:
  connect   Pantone Connect's own harmonies for that code, when the library came from
            a pantone-cli index (library meta `relationships`)
  computed  the anchor's OKLCh hue rotated by the harmony's angles (lightness and chroma
            kept), then snapped to the nearest color of the chosen book by CIEDE2000

A harmony is a starting point, not a theme: candidates still go through `audit`
(contrast, CVD and grayscale separation), which usually rejects some of them.
"""

from __future__ import annotations

import colorlib as cl
import library

# Hue offsets in degrees (OKLCh). MONOCHROMATIC keeps the hue and moves lightness.
OFFSETS = {
    "ANALOGOUS": (-30.0, 30.0),
    "COMPLEMENTARY": (180.0,),
    "SPLIT_COMPLEMENTARY": (150.0, 210.0),
    "TRIADIC": (120.0, 240.0),
    "TETRADIC": (90.0, 180.0, 270.0),
}
MONO_STEPS = (-0.16, -0.08, 0.08, 0.16)   # OKLCh L offsets
KINDS = (*OFFSETS, "MONOCHROMATIC")


def targets(hex_color: str, kind: str) -> list[str]:
    """The computed harmony colors of hex_color (sRGB, chroma reduced to fit)."""
    lightness_, chroma, hue = cl.to_oklch(hex_color)
    if kind == "MONOCHROMATIC":
        return [cl.oklch_to_hex(min(0.97, max(0.2, lightness_ + d)), chroma, hue) for d in MONO_STEPS]
    if kind not in OFFSETS:
        raise KeyError(f"unknown harmony {kind!r}; one of {KINDS}")
    return [cl.oklch_to_hex(lightness_, chroma, (hue + off) % 360) for off in OFFSETS[kind]]


def _connect(code: str | None, kind: str, libs: dict, meta: dict, book: str | None) -> list[dict]:
    if not code:
        return []
    key = library.norm_code(code)
    for name, m in meta.items():
        if book and library._slug(name) != library._slug(book) and name != book:
            continue
        rel = next((r for c, r in m["relationships"].items() if library.norm_code(c) == key), None)
        if not rel or kind not in rel["harmonies"]:
            continue
        out = []
        for ref in rel["harmonies"][kind]:
            hits = library.lookup_code(ref, libs, name) or library.lookup_code(ref, libs)
            if hits:
                hit_book, c = hits[0]
                out.append({"source": "connect", "target": c.hex, "code": c.code, "name": c.name,
                            "hex": c.hex, "delta_e": 0.0, "book": hit_book, "in_gamut": c.in_gamut})
        if out:
            return out
    return []


def harmonies(hex_color: str, code: str | None, libs: dict, meta: dict, book: str | None = None,
              kinds: tuple[str, ...] = KINDS) -> dict[str, list[dict]]:
    """kind -> [{source, target, code, name, hex, delta_e, book, in_gamut}]; without any
    library, code/hex are None and only the computed target is given."""
    out = {}
    for kind in kinds:
        found = _connect(code, kind, libs, meta, book)
        if not found:
            for target in targets(hex_color, kind):
                best = library.nearest(target, libs, book, top=1) if libs else []
                if best:
                    name, c, d = best[0]
                    found.append({"source": "computed", "target": target, "code": c.code, "name": c.name,
                                  "hex": c.hex, "delta_e": round(d, 2), "book": name, "in_gamut": c.in_gamut})
                else:
                    found.append({"source": "computed", "target": target, "code": None, "name": None,
                                  "hex": None, "delta_e": None, "book": None, "in_gamut": True})
        out[kind] = found
    return out
