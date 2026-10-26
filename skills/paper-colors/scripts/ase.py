"""Adobe Swatch Exchange (.ase) reader, for Pantone Connect collection exports.

Layout (all big-endian): b"ASEF", u16 major, u16 minor, u32 block count, then blocks of
u16 type + u32 length + body. Types: 0xC001 group start, 0xC002 group end, 0x0001 color.
Color body: u16 name length (UTF-16 units incl. NUL), UTF-16BE name, 4-byte model
("RGB ", "LAB ", "CMYK", "Gray"), float32 values, u16 color type (0 global, 1 spot, 2 normal).
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path

import colorlib as cl

GROUP_START, GROUP_END, COLOR = 0xC001, 0xC002, 0x0001
CHANNELS = {"RGB ": 3, "LAB ": 3, "CMYK": 4, "Gray": 1}

# Pantone code shapes: 00-0001 TCX / TPG / TPX / TSX, 0001 C / U / CP, P 000-1 C, Test Gray 10 C, ...
CODE_RE = re.compile(
    r"\b(\d{2}-\d{4} T[CPS]?[GX]"            # Fashion, Home + Interiors
    r"|P \d{1,3}-\d{1,2} [CU]"               # Pantone+ CMYK guide
    r"|(?:[A-Z][a-z]+ )*[A-Z]?[a-z]* ?\d{1,4} ?[A-Z]?\d?[A-Z]? ?(?:XGC|C|U|CP|UP|M)"  # solid / named
    r")\b")


@dataclass(frozen=True)
class Swatch:
    name: str            # as stored in the file
    code: str            # Pantone code parsed from the name
    model: str           # RGB / LAB / CMYK / Gray
    values: tuple[float, ...]
    group: str | None
    hex: str | None      # sRGB, None when the model cannot be converted (CMYK)
    note: str = ""


class AseError(ValueError):
    pass


def pantone_code(name: str) -> str:
    """'PANTONE 00-0001 TCX' -> '00-0001 TCX'; 'PANTONE Test Gray 10 C' -> 'Test Gray 10 C'."""
    bare = re.sub(r"^\s*PANTONE[®\s]*", "", name.strip(), flags=re.I)
    match = CODE_RE.search(bare)
    return " ".join((match.group(1) if match else bare).split())


def _to_hex(model: str, values: tuple[float, ...]) -> tuple[str | None, str]:
    if model == "RGB ":
        return cl.to_hex(values), ""
    if model == "Gray":
        return cl.to_hex((values[0],) * 3), ""
    if model == "LAB ":
        lab = (values[0] * 100, values[1], values[2])   # ASE stores L* as 0..1
        hex_c, ok = cl.lab_d50_to_hex(lab)
        return hex_c, "" if ok else "Lab outside sRGB, clipped"
    return None, "CMYK is device-dependent; re-export the collection as RGB/HEX"


def _read(data: bytes, offset: int, fmt: str) -> tuple[tuple, int]:
    size = struct.calcsize(fmt)
    if offset + size > len(data):
        raise AseError("file is truncated")
    return struct.unpack_from(fmt, data, offset), offset + size


def _name(body: bytes) -> tuple[str, int]:
    (units,), offset = _read(body, 0, ">H")
    raw = body[offset:offset + 2 * units]
    if len(raw) != 2 * units:
        raise AseError("color name is truncated")
    return raw.decode("utf-16-be").rstrip("\x00"), offset + 2 * units


def read_ase(path: Path) -> list[Swatch]:
    data = path.read_bytes()
    if data[:4] != b"ASEF":
        raise AseError(f"{path.name} is not an Adobe Swatch Exchange file")
    (_major, _minor, count), offset = _read(data, 4, ">HHI")
    swatches: list[Swatch] = []
    group = None
    for _ in range(count):
        (kind, length), offset = _read(data, offset, ">HI")
        body = data[offset:offset + length]
        if len(body) != length:
            raise AseError("block is truncated")
        offset += length
        if kind == GROUP_START:
            group = _name(body)[0]
        elif kind == GROUP_END:
            group = None
        elif kind == COLOR:
            name, pos = _name(body)
            model = body[pos:pos + 4].decode("ascii", errors="replace")
            if model not in CHANNELS:
                raise AseError(f"{name!r}: unknown color model {model!r}")
            values, _ = _read(body, pos + 4, f">{CHANNELS[model]}f")
            hex_c, note = _to_hex(model, values)
            swatches.append(Swatch(name, pantone_code(name), model.strip(), values, group, hex_c, note))
    return swatches


def write_ase(path: Path, colors: list[tuple[str, str, tuple[float, ...]]],
              group: str | None = None) -> None:
    """Write (name, model, values) entries; used by tests and to hand-make fixtures."""
    def name_bytes(name: str) -> bytes:
        text = (name + "\x00").encode("utf-16-be")
        return struct.pack(">H", len(text) // 2) + text

    blocks = []
    if group:
        blocks.append((GROUP_START, name_bytes(group)))
    for name, model, values in colors:
        body = (name_bytes(name) + model.ljust(4).encode("ascii")
                + struct.pack(f">{len(values)}f", *values) + struct.pack(">H", 1))
        blocks.append((COLOR, body))
    if group:
        blocks.append((GROUP_END, b""))
    out = b"ASEF" + struct.pack(">HHI", 1, 0, len(blocks))
    out += b"".join(struct.pack(">HI", kind, len(body)) + body for kind, body in blocks)
    path.write_bytes(out)
