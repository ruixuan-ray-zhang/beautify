"""Where the user's data lives: outside the skill, so reinstalling or updating the skill
never touches it.

$PAPER_COLORS_HOME (default ~/.paper-colors/)
  swatches.json      registered Pantone codes -> sRGB
  palettes.json      the user's themes (created from the bundled template by `init`)
  inbox/             screenshots and files waiting to be registered
  screenshots/       registered screenshots (provenance)
  imports/           imported .ase files (provenance)
  libraries/         indexed color books, a local matching index only
  verify/            Pantone Connect checklists

$PAPER_COLORS_SWATCHES and $PAPER_COLORS_PALETTES still override single files; the
other folders sit next to swatches.json.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_PALETTES = SKILL_DIR / "palettes.json"
DATA_DIRS = ("inbox", "screenshots", "imports", "libraries", "verify")
INBOX_NOTE = """Drop color material you are licensed to use here:
- color book files (.acb / .aco / .ase) to index once (`swatch library add`), or
- a collection exported from your Pantone Connect account as .ase (`swatch import`), or
- screenshots of color pages from your own account, one color each, code and HEX visible.
Nothing in this folder is part of the paper-colors skill or its repository; keep it out of git.
"""


def home() -> Path:
    return Path(os.environ.get("PAPER_COLORS_HOME", Path.home() / ".paper-colors")).expanduser()


def swatches() -> Path:
    return Path(os.environ.get("PAPER_COLORS_SWATCHES", home() / "swatches.json")).expanduser()


def palettes() -> Path:
    """The user's palettes.json; the bundled template until `init` has created one."""
    if "PAPER_COLORS_PALETTES" in os.environ:
        return Path(os.environ["PAPER_COLORS_PALETTES"]).expanduser()
    user = home() / "palettes.json"
    return user if user.exists() else TEMPLATE_PALETTES


def data_dir(name: str) -> Path:
    """inbox / screenshots / imports / libraries / verify, next to swatches.json."""
    if name not in DATA_DIRS:
        raise KeyError(f"unknown data folder {name!r}; one of {DATA_DIRS}")
    return swatches().parent / name


def init(source: Path | None = None) -> list[str]:
    """Create the data folder; with `source` (an old skill folder holding pantone/ and
    palettes.json) copy its registry, themes and color books over. Never overwrites
    user data; an untouched copy of the template counts as no themes yet."""
    for name in DATA_DIRS:
        data_dir(name).mkdir(parents=True, exist_ok=True)
    note = data_dir("inbox") / "README.md"
    if not note.exists():
        note.write_text(INBOX_NOTE)
    user_palettes = home() / "palettes.json"
    copies = []
    if source is not None:
        old = source.expanduser().resolve()
        copies += [(old / "palettes.json", user_palettes), (old / "pantone" / "swatches.json", swatches())]
        copies += [(old / "pantone" / name, data_dir(name)) for name in DATA_DIRS]
    copies.append((TEMPLATE_PALETTES, user_palettes))
    done = []
    for src, dst in copies:
        if not src.exists():
            continue
        if src.is_dir():
            for item in src.rglob("*"):
                target = dst / item.relative_to(src)
                if item.is_file() and not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, target)
                    done.append(str(target))
        elif not dst.exists() or (dst == user_palettes and src != TEMPLATE_PALETTES and _is_template(dst)):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            done.append(str(dst))
    return done


def _is_template(path: Path) -> bool:
    return path.read_bytes() == TEMPLATE_PALETTES.read_bytes()
