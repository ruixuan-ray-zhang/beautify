"""Light -> dark ramps of one hue: derived from an anchor, or checked when
they are an explicit list of book colors."""

from __future__ import annotations

import colorlib as cl

LIGHT_L = 92.0   # CIE L* of the lightest derived step (still visible on white)
DARK_L = 28.0    # CIE L* of the darkest derived step (still not black)
LIGHT_CHROMA = 0.30   # lightest step keeps this share of the anchor's chroma
DARK_CHROMA = 0.75    # darkest step keeps this share


def _targets(anchor_l: float, steps: int) -> tuple[list[float], int]:
    """Evenly spaced L* targets with the anchor occupying the nearest slot."""
    grid = [LIGHT_L + (DARK_L - LIGHT_L) * i / (steps - 1) for i in range(steps)]
    k = min(range(steps), key=lambda i: abs(grid[i] - anchor_l))
    top = max(LIGHT_L, anchor_l)
    bottom = min(DARK_L, anchor_l)
    lighter = [top + (anchor_l - top) * i / k for i in range(k)] if k else []
    n_dark = steps - 1 - k
    darker = [anchor_l + (bottom - anchor_l) * i / n_dark for i in range(1, n_dark + 1)]
    return lighter + [anchor_l] + darker, k


def _color_at(target_l: float, anchor_l: float, chroma: float, hue: float) -> str:
    """Hex with CIE L* == target_l on the anchor's OKLab hue, chroma tapering away from it."""
    if target_l >= anchor_l:
        share = 1 - (1 - LIGHT_CHROMA) * (target_l - anchor_l) / max(1e-6, LIGHT_L + 8 - anchor_l)
    else:
        share = 1 - (1 - DARK_CHROMA) * (anchor_l - target_l) / max(1e-6, anchor_l - DARK_L + 8)
    lo, hi = 0.0, 1.0
    for _ in range(40):  # OKLab L -> CIE L* is monotonic: bisect
        mid = (lo + hi) / 2
        if cl.lightness(cl.oklch_to_hex(mid, chroma * share, hue)) < target_l:
            lo = mid
        else:
            hi = mid
    return cl.oklch_to_hex((lo + hi) / 2, chroma * share, hue)


def derive(anchor_hex: str, steps: int = 5) -> tuple[list[str], int]:
    """-> (ramp light->dark with the anchor hex kept exactly, anchor index)."""
    if steps < 2:
        raise ValueError("a ramp needs at least 2 steps")
    anchor_l = cl.lightness(anchor_hex)
    _, chroma, hue = cl.to_oklch(anchor_hex)
    targets, k = _targets(anchor_l, steps)
    ramp = [anchor_hex if i == k else _color_at(t, anchor_l, chroma, hue)
            for i, t in enumerate(targets)]
    return ramp, k
