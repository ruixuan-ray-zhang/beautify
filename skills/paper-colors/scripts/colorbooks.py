"""Readers for digital color books: Adobe Color Book (.acb), Photoshop swatches (.aco),
Adobe Swatch Exchange (.ase). Every reader returns BookColor entries with a D65 Lab
value for matching (unclipped, so out-of-sRGB Pantone colors still compare correctly).

.acb (big-endian): b"8BCB", u16 version, u16 book id, then 4 strings (title, prefix,
postfix, description; each u32 UTF-16 length + UTF-16BE, may hold "$$$/key=Value"),
u16 color count, u16 page size, u16 page selector offset, u16 color type
(0 RGB, 2 CMYK, 7 Lab), then per color: string name, 6-byte ASCII key, components
(RGB 3 bytes, CMYK 4, Lab 3: L = byte * 100 / 255, a = byte - 128, b = byte - 128).

.aco (big-endian): version-1 block (u16 1, u16 count, count x [u16 space, 4 x u16]),
optionally followed by a version-2 block that repeats them with names
(u32 UTF-16 length incl. NUL + UTF-16BE). Spaces: 0 RGB (0..65535), 1 HSB,
2 CMYK, 7 Lab (L 0..10000, a/b signed /100), 8 Gray.
"""

from __future__ import annotations

import colorsys
import re
import struct
from dataclasses import dataclass
from pathlib import Path

import ase
import colorlib as cl


@dataclass(frozen=True)
class BookColor:
    code: str                              # Pantone code parsed from the full name
    name: str                              # full name as the book spells it
    model: str                             # Lab / RGB / HSB / CMYK / Gray
    lab: tuple[float, float, float] | None  # D65 Lab for matching; None = not convertible
    hex: str | None                        # sRGB (clipped when out of gamut)
    in_gamut: bool = True


class ColorBookError(ValueError):
    pass


class _Reader:
    def __init__(self, data: bytes, name: str):
        self.data, self.pos, self.name = data, 0, name

    def take(self, fmt: str) -> tuple:
        size = struct.calcsize(fmt)
        if self.pos + size > len(self.data):
            raise ColorBookError(f"{self.name}: file is truncated")
        values = struct.unpack_from(fmt, self.data, self.pos)
        self.pos += size
        return values

    def raw(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise ColorBookError(f"{self.name}: file is truncated")
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def utf16(self, length: int) -> str:
        return self.raw(2 * length).decode("utf-16-be", errors="replace").rstrip("\x00")


def _localized(text: str) -> str:
    """'$$$/colorbook/x/title=PANTONE+ Solid Coated' -> 'PANTONE+ Solid Coated'."""
    return text.split("=", 1)[1] if text.startswith("$$$") and "=" in text else text


def _from_lab_d50(lab: tuple[float, float, float]) -> tuple[tuple, str, bool]:
    hex_c, ok = cl.lab_d50_to_hex(lab)
    return cl.lab_d50_to_lab(lab), hex_c, ok


def _entry(full_name: str, model: str, lab=None, hex_c=None, ok=True) -> BookColor:
    if lab is None and hex_c is not None:
        lab = cl.to_lab(hex_c)
    return BookColor(ase.pantone_code(full_name), " ".join(full_name.split()), model, lab, hex_c, ok)


# ---------------------------------------------------------------------- ACB

def read_acb(path: Path) -> tuple[str, list[BookColor]]:
    r = _Reader(path.read_bytes(), path.name)
    if r.raw(4) != b"8BCB":
        raise ColorBookError(f"{path.name} is not an Adobe Color Book")
    r.take(">HH")                                     # version, book id
    title, prefix, postfix, _desc = (_localized(r.utf16(r.take(">I")[0])) for _ in range(4))
    count, _page, _offset, ctype = r.take(">HHHH")
    width = {0: 3, 2: 4, 7: 3}.get(ctype)
    if width is None:
        raise ColorBookError(f"{path.name}: unknown color type {ctype}")
    colors = []
    for _ in range(count):
        name = _localized(r.utf16(r.take(">I")[0]))
        key = r.raw(6).decode("ascii", errors="replace").strip()
        comps = r.raw(width)
        if not name.strip() and not key:
            continue                                  # empty page slot
        full = f"{prefix}{name}{postfix}"
        if ctype == 7:
            lab = (comps[0] * 100 / 255, comps[1] - 128, comps[2] - 128)
            colors.append(_entry(full, "Lab", *_from_lab_d50(lab)))
        elif ctype == 0:
            colors.append(_entry(full, "RGB", hex_c=cl.to_hex(tuple(c / 255 for c in comps))))
        else:
            colors.append(_entry(full, "CMYK"))       # device-dependent: no color
    return title or path.stem, colors


# ---------------------------------------------------------------------- ACO

_STRAY_ZERO = re.compile(r"(?<=[A-Za-z])0$")

def _aco_color(space: int, w: int, x: int, y: int, z: int, name: str) -> BookColor:
    if space == 0:
        return _entry(name, "RGB", hex_c=cl.to_hex((w / 65535, x / 65535, y / 65535)))
    if space == 1:
        rgb = colorsys.hsv_to_rgb(w / 65536, x / 65535, y / 65535)
        return _entry(name, "HSB", hex_c=cl.to_hex(rgb))
    if space == 7:
        sa, sb = struct.unpack(">hh", struct.pack(">HH", x, y))
        return _entry(name, "Lab", *_from_lab_d50((w / 100, sa / 100, sb / 100)))
    return _entry(name, {2: "CMYK", 8: "Gray"}.get(space, f"space{space}"))


def read_aco(path: Path) -> tuple[str, list[BookColor]]:
    r = _Reader(path.read_bytes(), path.name)
    version, count = r.take(">HH")
    if version not in (1, 2):
        raise ColorBookError(f"{path.name} is not a Photoshop swatch file")
    if version == 1:
        v1 = [r.take(">5H") for _ in range(count)]
        if r.pos + 4 <= len(r.data):
            version, count = r.take(">HH")             # optional named version-2 block
    if version == 2:
        records = []
        for _ in range(count):
            space, w, x, y, z = r.take(">5H")
            records.append((space, w, x, y, z, r.utf16(r.take(">I")[0]).strip()))
        names = [rec[-1] for rec in records]
        # Some third-party converters write an ASCII "0" where the NUL terminator belongs
        # ("PANTONE Test Yellow 12 C0"). Strip it only when nearly every name has it.
        if names and sum(bool(_STRAY_ZERO.search(n)) for n in names) >= 0.9 * len(names):
            records = [(*rec[:-1], _STRAY_ZERO.sub("", rec[-1])) for rec in records]
        return path.stem, [_aco_color(*rec) for rec in records]
    return path.stem, [_aco_color(*c, f"Swatch {i + 1}") for i, c in enumerate(v1)]


# ---------------------------------------------------------------------- ASE

def read_ase_book(path: Path) -> tuple[str, list[BookColor]]:
    colors = []
    for sw in ase.read_ase(path):
        if sw.model == "LAB":
            lab50 = (sw.values[0] * 100, sw.values[1], sw.values[2])
            colors.append(_entry(sw.name, "Lab", *_from_lab_d50(lab50)))
        elif sw.hex:
            colors.append(_entry(sw.name, sw.model, hex_c=sw.hex))
        else:
            colors.append(_entry(sw.name, sw.model))
    return path.stem, colors


def read_any(path: Path) -> tuple[str, list[BookColor]]:
    """Dispatch on the file's signature, not its extension."""
    head = path.read_bytes()[:4]
    if head == b"8BCB":
        return read_acb(path)
    if head == b"ASEF":
        return read_ase_book(path)
    if head[:2] in (b"\x00\x01", b"\x00\x02"):
        return read_aco(path)
    raise ColorBookError(f"{path.name}: not an ACB, ASE or ACO file (starts with {head!r}); "
                         "send this format as a sample so a reader can be added")
