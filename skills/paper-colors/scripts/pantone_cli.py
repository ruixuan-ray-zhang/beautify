"""Read an offline match index made by pantone-cli (https://github.com/malhashemi/pantone-cli).

pantone-cli ships no color data. The supported route is an index the user built from
their own licensed Pantone Connect account (`pantone-cli export`, then `pantone-cli index`).
This module reads that file in place; nothing of it is bundled with or copied by the skill.

Index (schemaVersion 1): {meta, books: [BookSummary], colorsByBook: {bookId: [color]},
relationshipsByColor: {"bookId\\x1fcode": {shades: {hue, lightness, saturation: [ref]},
harmonies: {ANALOGOUS, ...: [ref]}}}}; color = {code, name, hex "RRGGBB", lab {l, a, b}}
with Lab in D50; ref = {bookId, code}.

Lookup order for the index, as pantone-cli does it: --index, $PANTONE_INDEX,
./pantone-match-index.json, $PANTONE_CLI_HOME (default ~/.pantone-cli)/pantone-match-index.json.
"""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

import books
import colorbooks
import colorlib as cl
from colorbooks import BookColor

SCHEMA_VERSION = 1
INDEX_NAME = "pantone-match-index.json"
HARMONIES = ("ANALOGOUS", "COMPLEMENTARY", "MONOCHROMATIC", "SPLIT_COMPLEMENTARY", "TRIADIC", "TETRADIC")
SHADES = ("hue", "lightness", "saturation")


class PantoneCliIndexError(colorbooks.ColorBookError):
    pass


def candidates(explicit: str | None = None) -> list[Path]:
    cli_home = Path(os.environ.get("PANTONE_CLI_HOME", Path.home() / ".pantone-cli")).expanduser()
    raw = [explicit, os.environ.get("PANTONE_INDEX"), Path.cwd() / INDEX_NAME, cli_home / INDEX_NAME]
    return [Path(p).expanduser() for p in raw if p]


def find_index(explicit: str | None = None) -> Path:
    tried = candidates(explicit)
    for path in tried:
        if path.is_file():
            return path
    raise PantoneCliIndexError("no pantone-cli index found. Tried:\n" + "\n".join(f"  {p}" for p in tried)
                      + "\npantone-cli can build one from your own Pantone Connect account "
                        "(`pantone-cli export`, then `pantone-cli index`) where your license allows it; "
                        "or pass --index FILE.")


def load_index(path: Path) -> dict:
    data = path.read_bytes()
    if data[:2] == b"\x1f\x8b":
        try:
            data = gzip.decompress(data)
        except (OSError, EOFError) as exc:
            raise PantoneCliIndexError(f"{path}: damaged gzip file ({exc}); download the index again") from exc
    try:
        index = json.loads(data)
    except ValueError as exc:
        raise PantoneCliIndexError(f"{path}: not JSON ({exc})") from exc
    version = (index.get("meta") or {}).get("schemaVersion") if isinstance(index, dict) else None
    if version != SCHEMA_VERSION or not isinstance(index.get("colorsByBook"), dict):
        raise PantoneCliIndexError(f"{path}: not a pantone-cli match index with schemaVersion {SCHEMA_VERSION} "
                          f"(got {version!r})")
    return index


def is_index(path: Path) -> bool:
    try:
        load_index(path)
    except (PantoneCliIndexError, OSError):
        return False
    return True


def book_summaries(index: dict) -> list[dict]:
    known = {b.get("id"): b for b in index.get("books", [])}
    return [known.get(book_id, {"id": book_id, "title": book_id}) for book_id in index["colorsByBook"]]


def _color(entry: dict) -> BookColor | None:
    lab50, hex_raw = entry.get("lab"), entry.get("hex")
    hex_c = cl.to_hex(cl.parse_hex(hex_raw)) if hex_raw else None
    if lab50 and all(k in lab50 for k in "lab"):
        lab = (float(lab50["l"]), float(lab50["a"]), float(lab50["b"]))
        clipped, ok = cl.lab_d50_to_hex(lab)
        # Connect's own screen value beats our per-channel clipping for out-of-gamut colors.
        return BookColor(entry["code"], entry.get("name") or entry["code"], "Lab",
                         cl.lab_d50_to_lab(lab), hex_c or clipped, ok)
    if hex_c:
        return BookColor(entry["code"], entry.get("name") or entry["code"], "RGB", cl.to_lab(hex_c), hex_c)
    return None


def _refs(items) -> list[str]:
    return [r["code"] for r in items or [] if isinstance(r, dict) and r.get("code")]


def _relationships(index: dict, book_id: str) -> dict[str, dict]:
    out = {}
    prefix = f"{book_id}\x1f"
    for key, rel in (index.get("relationshipsByColor") or {}).items():
        if not key.startswith(prefix):
            continue
        harm = {k: _refs(v) for k, v in (rel.get("harmonies") or {}).items() if k in HARMONIES and _refs(v)}
        shades = {k: _refs((rel.get("shades") or {}).get(k)) for k in SHADES}
        entry = {"harmonies": harm, "shades": {k: v for k, v in shades.items() if v}}
        if entry["harmonies"] or entry["shades"]:
            out[rel.get("code") or key[len(prefix):]] = entry
    return out


def books_from_index(index: dict, wanted: list[str] | None = None) -> list[dict]:
    """-> [{title, book: describe-shape, colors: [BookColor], skipped, relationships}]."""
    summaries = {b["id"]: b for b in book_summaries(index)}
    if wanted:
        unknown = [w for w in wanted if w not in summaries]
        if unknown:
            raise PantoneCliIndexError(f"unknown book id(s) {unknown}; the index has {sorted(summaries)}")
    out = []
    for book_id in wanted or list(summaries):
        raw = index["colorsByBook"][book_id]
        colors = [c for c in (_color(e) for e in raw if e.get("code")) if c is not None]
        out.append({"title": summaries[book_id].get("title") or book_id,
                    "book": books.from_pantone_cli(summaries[book_id]),
                    "colors": colors, "skipped": len(raw) - len(colors),
                    "relationships": _relationships(index, book_id)})
    return out
