"""Local index of the user's licensed Pantone color books, and matching against it.

libraries/<slug>.json  parsed colors (code, name, model, D65 Lab, sRGB hex), in the data folder
libraries/source/      the original .acb / .aco / .ase files (a pantone-cli index is read in
                       place and not copied)
Each library also records its book (intended use, medium; see books.py) and, from a
pantone-cli index, Pantone Connect's shades and harmonies per code.
These stay on this machine: they are Pantone's licensed data. Only colors actually
used in a paper reach swatches.json and the exported files.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
from collections import Counter
from pathlib import Path

import books
import colorbooks
import colorlib as cl
from colorbooks import BookColor

GRADES = ((2.0, "match"), (5.0, "close"))   # dE2000 upper bounds; above: "far"
# What a CIEDE2000 distance looks like (upper bounds); above the last: no good match.
PERCEPTION = ((1.0, "not perceptible"), (2.0, "perceptible on close inspection"),
              (4.0, "noticeable"), (10.0, "clearly different"))
NO_GOOD_MATCH = "no good match in this book"
DISCLAIMER = ("Matching is CIEDE2000 against the book's Lab values: an approximation, not a "
              "substitute for Pantone Connect, physical Pantone guides or Pantone production "
              "guidance. Not affiliated with or endorsed by Pantone LLC; PANTONE® is a registered "
              "trademark of Pantone LLC.")


def grade(delta: float) -> str:
    return next((name for bound, name in GRADES if delta <= bound), "far")


def perceive(delta: float) -> str:
    return next((name for bound, name in PERCEPTION if delta < bound), NO_GOOD_MATCH)


def _slug(text: str) -> str:
    return re.sub(r"[^\w]+", "-", text).strip("-").lower() or "library"


def norm_code(code: str) -> str:
    return " ".join(code.split()).upper()


def add_library(src: Path, lib_dir: Path, name: str | None = None) -> tuple[str, dict]:
    """Parse a color book into lib_dir; returns (library name, stats)."""
    title, colors = colorbooks.read_any(src)
    usable = [c for c in colors if c.lab is not None]
    if not usable:
        raise colorbooks.ColorBookError(f"{src.name}: no colors with Lab/RGB values "
                                        f"(models: {dict(Counter(c.model for c in colors))})")
    name = name or title
    (lib_dir / "source").mkdir(parents=True, exist_ok=True)
    target = lib_dir / "source" / src.name
    if src.resolve() != target.resolve():
        shutil.copy2(src, target)
    _write(lib_dir, name, usable, source=f"source/{src.name}", book=books.describe(name))
    stats = {"colors": len(usable), "skipped": len(colors) - len(usable),
             "out_of_gamut": sum(not c.in_gamut for c in usable),
             "models": dict(Counter(c.model for c in colors))}
    return name, stats


def _write(lib_dir: Path, name: str, colors: list[BookColor], source: str,
           book: dict | None, relationships: dict | None = None) -> Path:
    entries = [{"code": c.code, "name": c.name, "model": c.model, "lab": [round(v, 4) for v in c.lab],
                "hex": c.hex, "in_gamut": c.in_gamut} for c in colors]
    body = {"name": name, "source": source, "added": dt.date.today().isoformat(),
            "book": book, "colors": entries}
    if relationships:
        body["relationships"] = relationships
    lib_dir.mkdir(parents=True, exist_ok=True)
    path = lib_dir / f"{_slug(name)}.json"
    path.write_text(json.dumps(body, ensure_ascii=False) + "\n")
    return path


def add_pantone_cli(index_path: Path, lib_dir: Path, wanted: list[str] | None = None) -> list[tuple[str, dict]]:
    """Index the books of a pantone-cli match index -> [(library name, stats)]."""
    import pantone_cli  # local: only this route needs it

    out = []
    entries = pantone_cli.books_from_index(pantone_cli.load_index(index_path), wanted)
    titles = Counter(_slug(e["title"]) for e in entries)
    for entry in entries:
        if not entry["colors"]:
            continue
        name = entry["title"] if titles[_slug(entry["title"])] == 1 else f"{entry['title']} ({entry['book']['id']})"
        _write(lib_dir, name, entry["colors"], source=f"pantone-cli:{index_path}",
               book=entry["book"], relationships=entry["relationships"])
        out.append((name, {"colors": len(entry["colors"]), "skipped": entry["skipped"],
                           "out_of_gamut": sum(not c.in_gamut for c in entry["colors"]),
                           "relationships": len(entry["relationships"]), "book": entry["book"]}))
    return out


def load_libraries(lib_dir: Path) -> dict[str, list[BookColor]]:
    libs: dict[str, list[BookColor]] = {}
    for path in sorted(lib_dir.glob("*.json")) if lib_dir.exists() else []:
        data = json.loads(path.read_text())
        libs[data["name"]] = [BookColor(e["code"], e["name"], e["model"], tuple(e["lab"]),
                                        e["hex"], e["in_gamut"]) for e in data["colors"]]
    return libs


def load_meta(lib_dir: Path) -> dict[str, dict]:
    """Library name -> {source, added, book, relationships, colors, out_of_gamut}."""
    meta: dict[str, dict] = {}
    for path in sorted(lib_dir.glob("*.json")) if lib_dir.exists() else []:
        data = json.loads(path.read_text())
        meta[data["name"]] = {
            "source": data.get("source", ""), "added": data.get("added", ""),
            "book": data.get("book") or books.describe(data["name"]),
            "relationships": data.get("relationships", {}),
            "colors": len(data["colors"]), "out_of_gamut": sum(not e["in_gamut"] for e in data["colors"])}
    return meta


def _select(libs: dict[str, list[BookColor]], library: str | None) -> dict[str, list[BookColor]]:
    if library is None:
        return libs
    picked = {n: c for n, c in libs.items() if n == library or _slug(n) == _slug(library)}
    if not picked:
        raise KeyError(f"no library {library!r}; have {sorted(libs)}")
    return picked


def lookup_code(code: str, libs: dict[str, list[BookColor]],
                library: str | None = None) -> list[tuple[str, BookColor]]:
    want = norm_code(code)
    return [(n, c) for n, colors in _select(libs, library).items() for c in colors
            if norm_code(c.code) == want]


def nearest(hex_color: str, libs: dict[str, list[BookColor]], library: str | None = None,
            top: int = 3) -> list[tuple[str, BookColor, float]]:
    """Closest book colors by CIEDE2000 (D65 Lab), best first."""
    target = cl.to_lab(hex_color)
    scored = [(n, c, cl.delta_e_lab(target, c.lab))
              for n, colors in _select(libs, library).items() for c in colors]
    return sorted(scored, key=lambda t: t[2])[:top]


# ------------------------------------------------------------------ resolution
# Rule for a palette entry: (1) the code itself, if any indexed book has it
# (a bare "00-0004" tries TCX, TPG; a bare "0001" tries C, U); (2) otherwise
# approximate its color, preferring a candidate LIGHTER than the target as long
# as it is at most LIGHTER_SLACK dE worse than the nearest one and within MAX_APPROX_DE.

SUFFIXES = {"fhi": ("TCX", "TPG", "TSX", "TN"), "pms": ("C", "U")}
LIGHTER_SLACK = 2.0
MAX_APPROX_DE = 5.0
PREFERENCES = ("lighter", "nearest", "darker")


def code_variants(code: str) -> list[str]:
    """'00-0004' -> ['00-0004 TCX', '00-0004 TPG', ...]; '0001' -> ['0001 C', '0001 U']."""
    base = " ".join(code.replace("PANTONE", "").split())
    if re.fullmatch(r"\d{2}-\d{4}", base):
        return [f"{base} {s}" for s in SUFFIXES["fhi"]]
    if re.fullmatch(r"\d{3,4}|[A-Za-z]+(?: [A-Za-z]+)* \d{0,3}", base) and not base[-1:].isalpha():
        return [f"{base} {s}" for s in SUFFIXES["pms"]]
    return [base]


def lookup_any(code: str, libs: dict[str, list[BookColor]],
               library: str | None = None) -> list[tuple[str, BookColor]]:
    """Exact lookup that also completes a missing library suffix, in SUFFIXES order."""
    for variant in code_variants(code):
        hits = lookup_code(variant, libs, library)
        if hits:
            return hits
    return []


def choose(target_hex: str, candidates: list[tuple[str, BookColor, float]],
           prefer: str = "lighter") -> tuple[tuple[str, BookColor, float] | None, str]:
    """Pick from nearest-first candidates -> (choice, reason)."""
    if not candidates:
        return None, "no candidates"
    nearest = candidates[0]
    if prefer == "nearest":
        return nearest, "nearest"
    target_l = cl.lightness(target_hex)
    side = [c for c in candidates
            if (c[1].lab[0] >= target_l if prefer == "lighter" else c[1].lab[0] <= target_l)
            and c[2] <= min(nearest[2] + LIGHTER_SLACK, MAX_APPROX_DE)]
    if side and side[0] is nearest:
        return nearest, f"nearest, and {prefer}"
    if side:
        return side[0], f"{prefer}: dE {side[0][2]:.1f} vs nearest {nearest[2]:.1f}"
    return nearest, f"nearest (no {prefer} candidate within dE {nearest[2] + LIGHTER_SLACK:.1f})"


def resolve(code: str | None, hex_color: str | None, libs: dict[str, list[BookColor]],
            library: str | None = None, prefer: str = "lighter", top: int = 8) -> dict:
    """Palette entry -> {status: exact|approx|far|none, chosen: (book, color, dE)|None,
    candidates: [...], reason}. `far` means even the choice is above MAX_APPROX_DE."""
    if code:
        hits = lookup_any(code, libs, library)
        if hits:
            name, color = hits[0]
            d = cl.delta_e(hex_color, color.hex) if hex_color else 0.0
            return {"status": "exact", "chosen": (name, color, d), "candidates": [], "reason": "code found"}
    if not hex_color:
        return {"status": "none", "chosen": None, "candidates": [],
                "reason": "code not in any indexed book and no color given to approximate"}
    cands = nearest(hex_color, libs, library, top)
    chosen, reason = choose(hex_color, cands, prefer)
    status = "approx" if chosen and chosen[2] <= MAX_APPROX_DE else "far"
    return {"status": status, "chosen": chosen, "candidates": cands, "reason": reason}
