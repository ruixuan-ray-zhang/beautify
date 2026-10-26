"""Pantone swatch registry (swatches.json in the data folder) and screenshot color sampling.

Registry values come from screenshots of Pantone Connect / pantone.com that the
user drops into the data folder's inbox/. Two readings per swatch:
  * transcribed: the HEX printed on the page (authoritative when visible)
  * sampled: the swatch pixels, converted from the screenshot's ICC profile to sRGB
They must agree within MAX_SAMPLE_DE, otherwise the screenshot is suspect.

Sampling needs Pillow (`uv run --with pillow python3 ...`); everything else is stdlib.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
from collections import Counter
from pathlib import Path

import colorlib as cl
import paths

SWATCHES_PATH = paths.swatches()
INBOX = paths.data_dir("inbox")
ARCHIVE = paths.data_dir("screenshots")
MAX_SAMPLE_DE = 3.0
CODE_RE = re.compile(r"^[\w][\w .\-]*[\w]$")


# ------------------------------------------------------------------ registry

def load_swatches(path: Path = SWATCHES_PATH) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {code: spec for code, spec in data.items() if not code.startswith("_")}


def _save(swatches: dict[str, dict], path: Path) -> None:
    body = {"_comment": "Pantone code -> sRGB hex. Add via `paper_colors.py swatch add`; "
                        "do not hand-edit hex values without a screenshot."}
    body.update(dict(sorted(swatches.items())))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n")


def add_swatch(code: str, name: str, hex_color: str | None, sampled: str | None,
               screenshot: Path | None, path: Path = SWATCHES_PATH,
               archive: Path = ARCHIVE) -> dict:
    """Validate and store one swatch; returns the stored entry. Raises ValueError."""
    code = " ".join(code.split())
    if not CODE_RE.match(code):
        raise ValueError(f"bad Pantone code {code!r} (e.g. '00-0001 TCX', '0001 C')")
    if not hex_color and not sampled:
        raise ValueError("need --hex (printed on the page) or --sampled (from `swatch sample`)")
    transcribed = cl.to_hex(cl.parse_hex(hex_color)) if hex_color else None
    measured = cl.to_hex(cl.parse_hex(sampled)) if sampled else None
    entry = {"name": name, "hex": transcribed or measured,
             "method": "transcribed" if transcribed else "sampled",
             "added": dt.date.today().isoformat()}
    if transcribed and measured:
        d = cl.delta_e(transcribed, measured)
        entry.update(sampled=measured, sample_delta_e=round(d, 2))
        if d > MAX_SAMPLE_DE:
            raise ValueError(f"page HEX {transcribed} and sampled {measured} differ by dE={d:.1f} "
                             f"(> {MAX_SAMPLE_DE}); re-check the screenshot or its color profile")
    if screenshot:
        archive.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^\w]+", "-", code).strip("-").lower()
        target = archive / f"{slug}{screenshot.suffix.lower()}"
        if screenshot.resolve() != target.resolve():
            shutil.move(str(screenshot), target)  # inbox -> archive keeps provenance
        entry["screenshot"] = str(target.relative_to(archive.parent))
    swatches = load_swatches(path)
    swatches[code] = entry
    _save(swatches, path)
    return entry


# ------------------------------------------------------------------ sampling

def _open_srgb(image_path: Path):
    """Open an image and convert it to sRGB using its embedded ICC profile.
    -> (PIL RGB image, profile description)."""
    try:
        import io
        from PIL import Image, ImageCms
    except ImportError as exc:
        raise RuntimeError("screenshot sampling needs Pillow: "
                           "uv run --with pillow python3 <skill>/scripts/paper_colors.py swatch sample ...") from exc
    with Image.open(image_path) as raw:
        icc = raw.info.get("icc_profile")
        img = raw.convert("RGBA").convert("RGB") if raw.mode in ("P", "LA", "RGBA") else raw.convert("RGB")
    if not icc:
        return img, "none embedded (assumed sRGB)"
    src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
    desc = ImageCms.getProfileDescription(src).strip()
    dst = ImageCms.createProfile("sRGB")
    converted = ImageCms.profileToProfile(img, src, dst, outputMode="RGB",
                                          renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC)
    return converted, desc


def dominant_colors(image_path: Path, box: tuple[int, int, int, int] | None = None,
                    top: int = 8) -> tuple[list[dict], str, tuple[int, int]]:
    """Largest uniform color areas (swatches are big flat rectangles).
    -> ([{hex, share, bbox, near_white}], profile description, image size)."""
    img, profile = _open_srgb(image_path)
    if box:
        img = img.crop(box)
    width, height = img.size
    stride = max(1, int((width * height / 400_000) ** 0.5))  # cap work at ~400k pixels
    pixels = img.load()
    buckets: Counter = Counter()
    exact: dict[tuple, Counter] = {}
    bounds: dict[tuple, list[int]] = {}
    for y in range(0, height, stride):
        for x in range(0, width, stride):
            rgb = pixels[x, y]
            key = tuple(c >> 3 for c in rgb)          # 32 levels per channel
            buckets[key] += 1
            exact.setdefault(key, Counter())[rgb] += 1
            b = bounds.setdefault(key, [x, y, x, y])
            b[0], b[1], b[2], b[3] = min(b[0], x), min(b[1], y), max(b[2], x), max(b[3], y)
    total = sum(buckets.values())
    out = []
    for key, count in buckets.most_common(top):
        rgb = exact[key].most_common(1)[0][0]
        hex_c = cl.to_hex(tuple(c / 255 for c in rgb))
        ox, oy = (box[0], box[1]) if box else (0, 0)
        x0, y0, x1, y1 = bounds[key]
        out.append({"hex": hex_c, "share": count / total,
                    "bbox": (x0 + ox, y0 + oy, x1 + ox, y1 + oy),
                    "near_white": cl.lightness(hex_c) > 97})
    return out, profile, img.size


def inbox_files(inbox: Path = INBOX) -> list[Path]:
    exts = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".heic"}
    return sorted(p for p in inbox.glob("*") if p.suffix.lower() in exts) if inbox.exists() else []


# ------------------------------------------------------------------ ASE import

def import_ase(ase_path: Path, path: Path = SWATCHES_PATH, imports: Path | None = None,
               dry_run: bool = False) -> list[dict]:
    """Register every swatch of a Pantone Connect .ase export.

    Returns one report row per swatch: {code, hex, status, detail} with status
    added / unchanged / conflict / skipped. Existing entries are never overwritten:
    a different color under a known code is a conflict for the user to resolve.
    """
    import ase  # local: only this command needs it

    swatches = load_swatches(path)
    imports = imports or path.parent / "imports"
    today = dt.date.today().isoformat()
    report, added, seen = [], {}, {}
    for sw in ase.read_ase(ase_path):
        row = {"code": sw.code, "hex": sw.hex, "name": sw.name}
        if not sw.hex:
            report.append({**row, "status": "skipped", "detail": sw.note})
            continue
        if not CODE_RE.match(sw.code):
            report.append({**row, "status": "skipped", "detail": "no Pantone code in the name"})
            continue
        known = swatches.get(sw.code, {}).get("hex") or seen.get(sw.code)
        if known:
            d = cl.delta_e(known, sw.hex)
            status = "unchanged" if d <= MAX_SAMPLE_DE else "conflict"
            report.append({**row, "status": status,
                           "detail": f"registered as {known} (dE {d:.1f})"})
            continue
        seen[sw.code] = sw.hex
        added[sw.code] = {"name": sw.name, "hex": sw.hex, "method": f"ase-{sw.model.lower()}",
                          "source": f"imports/{ase_path.name}", "added": today,
                          **({"group": sw.group} if sw.group else {}),
                          **({"note": sw.note} if sw.note else {})}
        report.append({**row, "status": "added", "detail": sw.note or sw.model})
    if added and not dry_run:
        imports.mkdir(parents=True, exist_ok=True)
        if ase_path.resolve() != (imports / ase_path.name).resolve():
            shutil.copy2(ase_path, imports / ase_path.name)
        _save({**swatches, **added}, path)
    return report


def register_from_library(color, library_name: str, path: Path = SWATCHES_PATH) -> str:
    """Store a color book's value for its code -> added / unchanged / conflict ..."""
    swatches = load_swatches(path)
    code = " ".join(color.code.split())
    if code in swatches:
        d = cl.delta_e(swatches[code]["hex"], color.hex)
        if d <= MAX_SAMPLE_DE:
            return "unchanged"
        return f"conflict (registered {swatches[code]['hex']}, dE {d:.1f})"
    entry = {"name": color.name, "hex": color.hex, "method": "library",
             "source": library_name, "added": dt.date.today().isoformat()}
    if not color.in_gamut:
        entry["note"] = "outside sRGB; hex is the clipped screen approximation"
    swatches[code] = entry
    _save(swatches, path)
    return "added"
