"""Find colors in a paper project that are not part of the chosen theme.

Allowed: the theme's anchors and every ramp step, their tints / shades
(what xcolor `cOurs!20`, `tint()` or alpha on white produce), and neutral grays.
Flagged: any other hex / rgb literal, named colors (xcolor, TikZ, matplotlib,
SVG, draw.io), rainbow colormaps.

Not detected: colors computed at runtime (e.g. from a variable or a loop).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import colorlib as cl
from exporters import tex_color_names
from themes import Theme

SCAN_SUFFIXES = {".py", ".ipynb", ".tex", ".sty", ".tikz", ".svg", ".drawio", ".json"}
TEX_SUFFIXES = {".tex", ".sty", ".tikz"}
PY_SUFFIXES = {".py", ".ipynb"}
MARKUP_SUFFIXES = {".svg", ".drawio"}
GENERATED = {"paper_colors.py", "paper-colors.sty", "paper-colors.json", "paper-colors-swatches.svg"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist"}
MAX_BYTES = 2_000_000

MATCH_DE = 3.0          # within this CIEDE2000 of a role / tint / shade => on palette
GRAY_CHROMA = 4.0       # Lab chroma below this counts as neutral gray
RAINBOW = {"jet", "rainbow", "hsv", "gist_rainbow", "nipy_spectral", "gist_ncar", "turbo"}
NEUTRAL_NAMES = {"black", "white", "gray", "grey", "darkgray", "lightgray", "k", "w",
                 "none", "transparent", "currentcolor", "inherit", "url", "default", "."}
# Bare TikZ option tokens (`\draw[red]`) are only colors if they are one of these.
XCOLOR_NAMES = {"red", "green", "blue", "cyan", "magenta", "yellow", "brown", "lime", "olive",
                "orange", "pink", "purple", "teal", "violet"}
TIKZ_COLOR_KEYS = {"draw", "fill", "color", "text", "top color", "bottom color", "left color",
                   "right color", "ball color", "inner color", "outer color", "middle color",
                   "mark color", "fill color"}

HEX_RE = re.compile(r"(?<![\w&/=#.\\])#([0-9A-Fa-f]{6})(?:[0-9A-Fa-f]{2})?(?![0-9A-Za-z_])")
TEX_COMMENT_RE = re.compile(r"(?<!\\)%.*")
TEX_LINK_RE = re.compile(r"\\(?:href|url)\{[^}]*\}")
TEX_DEF_RE = re.compile(r"\\(?:definecolor|colorlet|providecolor)\{([^}]+)\}")
TEX_DEF_VALUE_RE = re.compile(r"\\(?:definecolor|providecolor)\{[^}]+\}\{(\w+)\}\{([^}]+)\}")
TEX_COLORLET_RE = re.compile(r"\\colorlet\{[^}]+\}\{([^}]+)\}")
TEX_USE_RE = re.compile(r"\\(?:textcolor|color|colorbox|cellcolor|rowcolor|columncolor|pagecolor)"
                        r"(?:\[([^\]]*)\])?\{([^}#]+)\}")
TEX_FCOLORBOX_RE = re.compile(r"\\fcolorbox(?:\[([^\]]*)\])?\{([^}#]+)\}\{([^}#]+)\}")
TIKZ_KEYVAL_RE = re.compile(r"\b(" + "|".join(sorted(TIKZ_COLOR_KEYS, key=len, reverse=True))
                            + r")\s*=\s*([A-Za-z][\w!.\-]*)")
TIKZ_OPTS_RE = re.compile(r"\\(?:draw|fill|filldraw|path|node|shade|shadedraw|addplot3?\+?|"
                          r"begin\{(?:axis|tikzpicture|scope)\})\s*\[([^\]]*)\]")
TEX_CMAP_RE = re.compile(r"colormap(?:/|\s+name\s*=\s*)(\w+)")
PY_KW = (r"color|c|colors|facecolor|edgecolor|fc|ec|mfc|mec|markerfacecolor|"
         r"markeredgecolor|ecolor|fill_color|line_color")
PY_COLOR_RE = re.compile(r"(?:\b(?:" + PY_KW + r")\s*=\s*|['\"](?:" + PY_KW + r")['\"]\s*:\s*)"
                         r"(\[[^\]]*\]|\([^)]*\)|'[^']*'|\"[^\"]*\")")
PY_SUBSCRIPT_RE = re.compile(r"\b\w+\[\s*['\"][^'\"]*['\"]\s*\]")
PY_STR_RE = re.compile(r"['\"]([^'\"]*)['\"]")
PY_RAINBOW_RE = re.compile(r"(?:['\"]|\bcm\.)(" + "|".join(RAINBOW) + r")(?:_r)?(?:['\"]|\b)")
PY_FMT_RE = re.compile(r"\.(?:plot|errorbar|semilogx|semilogy|loglog|step)\(.*?['\"]"
                       r"([bgrcmy])[-:.]{0,2}[.,ov^<>sp*hH+xXDd|_1-4]?[-:.]{0,2}['\"]")
MARKUP_RGB_RE = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)")
MARKUP_NAMED_RE = re.compile(r"\b(?:fill|stroke|stop-color|flood-color|color|fillColor|strokeColor|"
                             r"fontColor|gradientColor|labelBackgroundColor)\s*[=:]\s*\"?([A-Za-z]+)\b(?!\s*\()")


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    kind: str
    value: str
    hint: str

    def format(self, root: Path) -> str:
        rel = self.path.relative_to(root) if self.path.is_relative_to(root) else self.path
        return f"{rel}:{self.line}: [{self.kind}] {self.value} -> {self.hint}"


def _references(theme: Theme) -> dict[str, str]:
    refs = dict(theme.colors)
    refs.update({f"{role}@{k}": c for role, ramp in theme.ramps.items()
                 for k, c in enumerate(ramp, 1)})
    refs["arrow"] = theme.arrow
    return refs


_CLASSIFY_CACHE: dict[tuple[str, str], str | None] = {}


def classify_hex(hex_color: str, theme: Theme) -> str | None:
    """None if on-palette, else a hint naming the closest role. Cached per (theme, hex)."""
    key = (theme.name, hex_color.upper())
    if key not in _CLASSIFY_CACHE:
        _CLASSIFY_CACHE[key] = _classify_uncached(key[1], theme)
    return _CLASSIFY_CACHE[key]


def _classify_uncached(hex_color: str, theme: Theme) -> str | None:
    _, a, b = cl.to_lab(hex_color)
    if math.hypot(a, b) < GRAY_CHROMA:
        return None
    best_name, best_d = "", float("inf")
    for name, ref in _references(theme).items():
        t, d = cl.nearest_tint(hex_color, ref)
        if d < MATCH_DE:
            return None
        if any(cl.delta_e(hex_color, cl.shade(ref, s / 100)) < MATCH_DE for s in range(30, 100, 5)):
            return None
        if d < best_d:
            best_name, best_d = (f"{name} tinted {round(t * 100)}%" if t < 1 else name), d
    return f"off-palette; closest is {best_name} (dE={best_d:.1f}). Use the role, not a new hex"


def _model_to_hex(model: str, value: str) -> str | None:
    """xcolor (model, value) -> hex; None for models we do not convert."""
    model, parts = model.strip(), [p.strip() for p in value.split(",")]
    try:
        if model == "HTML":
            return cl.to_hex(cl.parse_hex(value))
        if model in ("rgb", "RGB") and len(parts) == 3:
            scale = 255 if model == "RGB" else 1
            return cl.to_hex(tuple(float(p) / scale for p in parts))
        if model == "gray" and len(parts) == 1:
            return "#808080"  # any gray is allowed
    except ValueError:
        return None
    return None


def _allowed_tex_names(theme: Theme, defined: set[str]) -> set[str]:
    return {n.lower() for n in tex_color_names(theme) | defined} | NEUTRAL_NAMES


def _tex_expr_bad_names(expr: str, allowed: set[str]) -> list[str]:
    """xcolor expression like `cOurs!20!white` -> names not allowed."""
    parts = [p.strip() for p in expr.split("!")]
    return [p for p in parts if p and not p.lstrip("-").replace(".", "").isdigit()
            and p.lower() not in allowed]


class _Collector:
    def __init__(self, path: Path, theme: Theme):
        self.path, self.theme = path, theme
        self.findings: list[Finding] = []
        self._seen: set[tuple[int, str, str]] = set()

    def add(self, line: int, kind: str, value: str, hint: str) -> None:
        if (line, kind, value) not in self._seen:
            self._seen.add((line, kind, value))
            self.findings.append(Finding(self.path, line, kind, value, hint))

    def hex(self, line: int, hex_color: str, shown: str | None = None, kind: str = "hex") -> None:
        hint = classify_hex(hex_color, self.theme)
        if hint:
            self.add(line, kind, shown or hex_color.upper(), hint)


def _lint_tex_line(col: _Collector, n: int, code: str, allowed: set[str]) -> None:
    def check_expr(expr: str) -> None:
        for bad in _tex_expr_bad_names(expr, allowed):
            col.add(n, "tex-name", bad, "named color outside the theme; use cOurs / cBase1 / cOursS3 ...")

    for h in re.findall(r"\{HTML\}\{([0-9A-Fa-f]{6})\}", code):
        col.hex(n, "#" + h)
    for model, value in TEX_DEF_VALUE_RE.findall(code):
        hex_c = _model_to_hex(model, value) if model != "HTML" else None
        if hex_c:
            col.hex(n, hex_c, f"{{{model}}}{{{value}}}", "rgb")
    for expr in TEX_COLORLET_RE.findall(code):
        check_expr(expr)
    for model, value in TEX_USE_RE.findall(code):
        if model:
            hex_c = _model_to_hex(model, value)
            if hex_c:
                col.hex(n, hex_c, f"[{model}]{{{value}}}", "rgb")
        else:
            check_expr(value)
    for model, *values in TEX_FCOLORBOX_RE.findall(code):
        for value in values:
            hex_c = _model_to_hex(model, value) if model else None
            if hex_c:
                col.hex(n, hex_c, f"[{model}]{{{value}}}", "rgb")
            elif not model:
                check_expr(value)
    for _key, expr in TIKZ_KEYVAL_RE.findall(code):
        check_expr(expr)
    for opts in TIKZ_OPTS_RE.findall(code):
        for token in (t.strip() for t in opts.split(",")):
            head = token.split("!")[0].strip().lower()
            if "=" not in token and head in XCOLOR_NAMES and head not in allowed:
                check_expr(token)
    for cmap in TEX_CMAP_RE.findall(code):
        if cmap.lower() in RAINBOW:
            col.add(n, "rainbow-cmap", cmap, "not perceptually uniform; use paperseq / paperdiv / viridis")


def _lint_py_line(col: _Collector, n: int, code: str) -> None:
    lookups_removed = PY_SUBSCRIPT_RE.sub("_", code)  # C["ours"] is a role lookup, not a color name
    for value in PY_COLOR_RE.findall(lookups_removed):
        strings = PY_STR_RE.findall(value)
        if not strings and value.startswith("("):
            nums = re.findall(r"[\d.]+", value)
            if len(nums) in (3, 4) and all(0 <= float(x) <= 1 for x in nums[:3]):
                col.hex(n, cl.to_hex(tuple(float(x) for x in nums[:3])), value, "rgb")
        for s in strings:
            low = s.lower().strip()
            if (not low or low.startswith("#") or low in NEUTRAL_NAMES or re.fullmatch(r"c\d", low)
                    or low.replace(".", "", 1).isdigit()):
                continue
            col.add(n, "mpl-name", s, 'named color; use C["ours"] / C["base1"] / style(i)')
    for letter in PY_FMT_RE.findall(code):
        col.add(n, "mpl-name", letter, "color letter in a plot format string; pass color=C[...]")
    for cmap in PY_RAINBOW_RE.findall(code):
        col.add(n, "rainbow-cmap", cmap, "not perceptually uniform; use paper_sequential, cividis or viridis")


def _lint_markup_line(col: _Collector, n: int, code: str) -> None:
    for r, g, b in MARKUP_RGB_RE.findall(code):
        col.hex(n, cl.to_hex(tuple(int(v) / 255 for v in (r, g, b))), f"rgb({r},{g},{b})", "rgb")
    for name in MARKUP_NAMED_RE.findall(code):
        if name.lower() not in NEUTRAL_NAMES:
            col.add(n, "named", name, "named color; use the theme hex from paper-colors.json")


def lint_text(path: Path, text: str, theme: Theme, defined: set[str] | None = None) -> list[Finding]:
    """`defined`: color names defined anywhere in the project (\\definecolor / \\colorlet)."""
    suffix = path.suffix
    if suffix == ".ipynb":
        text = text.replace('\\"', '"')  # notebook sources are JSON-escaped
    is_tex = suffix in TEX_SUFFIXES
    allowed = _allowed_tex_names(theme, (defined or set()) | set(TEX_DEF_RE.findall(text)))
    col = _Collector(path, theme)
    for n, line in enumerate(text.splitlines(), 1):
        code = TEX_LINK_RE.sub("", TEX_COMMENT_RE.sub("", line)) if is_tex else line
        for h in HEX_RE.findall(code):
            col.hex(n, "#" + h)
        if is_tex:
            _lint_tex_line(col, n, code, allowed)
        elif suffix in PY_SUFFIXES:
            _lint_py_line(col, n, code)
        elif suffix in MARKUP_SUFFIXES:
            _lint_markup_line(col, n, code)
    return col.findings


def iter_files(root: Path):
    if root.is_file():
        yield root
        return
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and path.suffix in SCAN_SUFFIXES and path.name not in GENERATED:
            if path.stat().st_size <= MAX_BYTES:
                yield path


def detect_theme(root: Path) -> str | None:
    """Read the theme name recorded in an exported paper-colors.sty / paper_colors.py."""
    base = root if root.is_dir() else root.parent
    for pattern, regex in (("paper-colors.sty", r"theme ([\w-]+)\. GENERATED"),
                           ("paper_colors.py", r'^THEME = "([\w-]+)"')):
        for path in base.rglob(pattern):
            match = re.search(regex, path.read_text(errors="ignore"), re.M)
            if match:
                return match.group(1)
    return None


def lint_tree(root: Path, theme: Theme) -> list[Finding]:
    texts: dict[Path, str] = {}
    findings: list[Finding] = []
    for path in iter_files(root):
        try:
            texts[path] = path.read_text(errors="ignore")
        except OSError as exc:
            findings.append(Finding(path, 0, "io-error", str(exc), "could not read file"))
    defined = {name for path, text in texts.items() if path.suffix in TEX_SUFFIXES
               for name in TEX_DEF_RE.findall(TEX_COMMENT_RE.sub("", text))}
    for path, text in texts.items():
        findings.extend(lint_text(path, text, theme, defined))
    return findings
