"""Check color values against Pantone Connect, the authoritative source.

1. `checklist` writes a TSV of codes with the value we hold (registered swatch or color book)
   and an empty `connect_hex` column under verify/ in the data folder.
2. The user looks each code up in Pantone Connect and fills in the HEX it shows
   (or pastes "CODE  #HEX" lines in any order).
3. `compare` reports the CIEDE2000 difference per code; registered swatches get a
   `verified` record, and with adopt=True their hex becomes Connect's value.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import random
import re
from pathlib import Path

import colorlib as cl

OK_DE, CHECK_DE = 2.0, 5.0
FIELDS = ["code", "source", "our_hex", "outside_srgb", "connect_hex"]
LINE_RE = re.compile(r"^\s*(?P<code>.+?)[\s,;:|]+#?(?P<hex>[0-9A-Fa-f]{6})\s*$")


def norm(code: str) -> str:
    return " ".join(code.replace("PANTONE", "").split()).upper()


def status(delta: float) -> str:
    return "ok" if delta <= OK_DE else "check" if delta <= CHECK_DE else "mismatch"


def sample_codes(colors: list, k: int, seed: int) -> list:
    """Spread a sample over the book's lightness range instead of pure random picks."""
    ranked = sorted(colors, key=lambda c: c.lab[0])
    rng = random.Random(seed)
    k = min(k, len(ranked))
    bins = [ranked[i * len(ranked) // k:(i + 1) * len(ranked) // k] for i in range(k)]
    return [rng.choice(b) for b in bins if b]


def write_checklist(rows: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, FIELDS, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({**{f: "" for f in FIELDS}, **row})
    return path


def parse_values(text: str) -> tuple[dict[str, str], dict[str, dict]]:
    """-> ({normalized code: connect hex}, {normalized code: checklist row}).
    Accepts a filled checklist TSV or free 'CODE  #HEX' lines."""
    connect, rows = {}, {}
    if text.lstrip().startswith("code\t"):
        for row in csv.DictReader(io.StringIO(text), delimiter="\t"):
            key = norm(row["code"])
            rows[key] = row
            value = (row.get("connect_hex") or "").strip()
            if value:
                connect[key] = cl.to_hex(cl.parse_hex(value))
        return connect, rows
    for line in text.splitlines():
        match = LINE_RE.match(line)
        if match:
            connect[norm(match["code"])] = cl.to_hex(cl.parse_hex(match["hex"]))
    return connect, rows


def compare(connect: dict[str, str], expected: dict[str, dict]) -> list[dict]:
    """expected: normalized code -> {code, source, our_hex, outside_srgb}."""
    report = []
    for key, connect_hex in connect.items():
        exp = expected.get(key)
        if not exp:
            report.append({"code": key, "connect_hex": connect_hex, "status": "unknown"})
            continue
        d = cl.delta_e(exp["our_hex"], connect_hex)
        report.append({**exp, "connect_hex": connect_hex, "delta_e": round(d, 2), "status": status(d)})
    for key, exp in expected.items():
        if key not in connect:
            report.append({**exp, "status": "missing"})
    return report


def record(swatches: dict[str, dict], report: list[dict], adopt: bool) -> list[str]:
    """Write `verified` into registered swatches; adopt=True takes Connect's hex. -> codes updated."""
    today = dt.date.today().isoformat()
    by_norm = {norm(code): code for code in swatches}
    updated = []
    for row in report:
        code = by_norm.get(norm(row["code"]))
        if not code or "delta_e" not in row:
            continue
        entry = swatches[code]
        entry["verified"] = {"connect_hex": row["connect_hex"], "delta_e": row["delta_e"],
                             "status": row["status"], "date": today}
        if adopt and entry["hex"] != row["connect_hex"]:
            entry.setdefault("book_hex", entry["hex"])
            entry["hex"] = row["connect_hex"]
        updated.append(code)
    return updated
