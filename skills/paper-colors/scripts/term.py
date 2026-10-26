"""Terminal color swatches: on only for a TTY, off with a non-empty $NO_COLOR or --no-color."""

from __future__ import annotations

import os
import sys

import colorlib as cl

_forced_off = False


def disable(off: bool = True) -> None:
    global _forced_off
    _forced_off = off


def enabled() -> bool:
    return not _forced_off and not os.environ.get("NO_COLOR") and sys.stdout.isatty()


def swatch(hex_color: str | None) -> str:
    """A 3-cell 24-bit color block plus a space, or '' when swatches are off."""
    if not hex_color or not enabled():
        return ""
    r, g, b = (round(c * 255) for c in cl.parse_hex(hex_color))
    return f"\x1b[48;2;{r};{g};{b}m   \x1b[0m "
