"""Load color themes from palettes.json + swatches.json (in the data folder), derive ramps
and every secondary color, and audit them."""

from __future__ import annotations

import itertools
import json
import os
from dataclasses import dataclass
from pathlib import Path

import colorlib as cl
import registry
import paths
import ramps


def palettes_path() -> Path:
    """palettes.json in the data folder (see paths.py), read on every call."""
    return paths.palettes()


def swatches_path() -> Path:
    """swatches.json in the data folder (see paths.py), read on every call."""
    return paths.swatches()

REQUIRED_HUES = ("ours", "base1", "base2", "base3", "neutral")
OPTIONAL_HUES = ("base4", "base5")
TEXT_ROLES = ("highlight", "gain", "drop", "link")

# Acceptance thresholds. Every theme must pass all ERROR rules (reasons: references/theory.md).
MIN_LINE_CONTRAST = 3.0        # ours, base1-3 anchors on white
MIN_ANY_CONTRAST = 2.0         # base4/5, neutral anchors
MIN_TEXT_CONTRAST = 4.5        # gain / drop / link
MIN_DE_NORMAL = 15.0           # CIEDE2000 between any two anchors
MIN_DE_CVD = 10.0              # under protan/deutan/tritan, first CVD_CORE anchors
CVD_CORE = 4
MIN_GRAY_GAP = 10.0            # L* gap ours vs base1-3
MIN_GRAY_PAIR = 8.0            # L* gap for two series to differ in grayscale alone
MIN_HIGHLIGHT_L = 90.0
MIN_RAMP_STEP = 8.0            # L* between neighbouring ramp steps (ERROR below)
GOOD_RAMP_STEP = 11.0          # WARN below
MAX_RAMP_HUE_SPREAD = 30.0     # OKLCh degrees, chromatic Pantone ramps (WARN above)
MIN_DE_FILLS = 4.0
MAX_DIV_IMBALANCE = 15.0


class ThemeError(ValueError):
    pass


@dataclass(frozen=True)
class Theme:
    name: str
    description: str
    anchors: dict[str, str]              # hue role -> anchor hex
    codes: dict[str, str]                # hue role -> anchor Pantone code
    ramps: dict[str, list[str]]          # hue role -> hex, light -> dark
    ramp_codes: dict[str, list]          # hue role -> Pantone code per step (None = derived)
    anchor_step: dict[str, int]          # hue role -> 1-based step of the anchor
    text: dict[str, str]                 # highlight/gain/drop/link -> hex
    text_refs: dict[str, str]            # e.g. {"gain": "base2@5"}
    diverging_roles: tuple[str, str]
    arrow: str
    diagram_roles: dict[str, str]

    @property
    def hues(self) -> list[str]:
        return [r for r in ("ours", "base1", "base2", "base3") + OPTIONAL_HUES + ("neutral",)
                if r in self.anchors]

    @property
    def series(self) -> list[str]:
        """style(i) order: ours, base1, base2, ..."""
        return [r for r in self.hues if r != "neutral"]

    @property
    def colors(self) -> dict[str, str]:
        return {**self.anchors, **self.text}

    @property
    def cycle(self) -> list[str]:
        return [self.anchors[r] for r in self.hues]

    def step(self, ref: str) -> str:
        """'base2@5' -> hex of step 5 (1 = lightest)."""
        role, _, k = ref.partition("@")
        if role not in self.ramps or not k.isdigit() or not 1 <= int(k) <= len(self.ramps[role]):
            raise ThemeError(f"{self.name}: bad step reference {ref!r}")
        return self.ramps[role][int(k) - 1]

    @property
    def sequential(self) -> list[str]:
        return list(self.ramps["ours"])

    @property
    def diverging(self) -> list[str]:
        neg, pos = (self.ramps[r] for r in self.diverging_roles)
        return [neg[-1], neg[len(neg) // 2], self.ramps["neutral"][0], pos[len(pos) // 2], pos[-1]]

    @property
    def diagram(self) -> dict[str, dict[str, str]]:
        return {role: {"stroke": self.anchors[src], "fill": self.ramps[src][0], "source": src}
                for role, src in self.diagram_roles.items()}


def _hex_for(code: str, swatches: dict, theme: str) -> str:
    if code not in swatches:
        raise ThemeError(f"{theme}: Pantone {code!r} is not in swatches.json; "
                         "add it from a screenshot first (`paper_colors.py swatch add`)")
    return cl.to_hex(cl.parse_hex(swatches[code]["hex"]))


def _build_hue(name: str, role: str, hue, steps: int, swatches: dict) -> tuple:
    """-> (anchor hex, anchor code, ramp, ramp codes, 1-based anchor step)."""
    hue = hue if isinstance(hue, dict) else {"anchor": hue}
    code = hue["anchor"]
    anchor = _hex_for(code, swatches, name)
    if "ramp" in hue:
        listed = list(hue["ramp"])
        if code not in listed:
            raise ThemeError(f"{name}: {role} ramp must contain its anchor {code!r}")
        return anchor, code, [_hex_for(c, swatches, name) for c in listed], listed, listed.index(code) + 1
    derived, k = ramps.derive(anchor, steps)
    return anchor, code, derived, [code if i == k else None for i in range(steps)], k + 1


def _build(name: str, spec: dict, defaults: dict, swatches: dict) -> Theme:
    steps = int(spec.get("steps", defaults.get("steps", 5)))
    hues = spec.get("hues", {})
    missing = [r for r in REQUIRED_HUES if r not in hues]
    if missing:
        raise ThemeError(f"{name}: missing hues {missing}")
    fields: dict[str, dict] = {k: {} for k in ("anchors", "codes", "ramps", "ramp_codes", "anchor_step")}
    for role in REQUIRED_HUES + OPTIONAL_HUES:
        if role in hues:
            for key, value in zip(fields, _build_hue(name, role, hues[role], steps, swatches)):
                fields[key][role] = value
    theme = Theme(name=name, description=spec.get("description", ""), **fields, text={},
                  text_refs=dict(spec.get("text", {})),
                  diverging_roles=tuple(spec.get("diverging", ("base1", "ours"))),
                  arrow="#000000", diagram_roles=dict(spec.get("diagram", defaults["diagram"])))
    missing_text = [r for r in TEXT_ROLES if r not in theme.text_refs]
    if missing_text:
        raise ThemeError(f"{name}: 'text' needs {missing_text} as 'role@step' references")
    unknown = [s for s in (*theme.diverging_roles, *theme.diagram_roles.values())
               if s not in theme.anchors]
    if unknown:
        raise ThemeError(f"{name}: diverging / diagram refer to undefined hues {unknown}")
    text = {r: theme.step(theme.text_refs[r]) for r in TEXT_ROLES}
    arrow = theme.step(spec.get("arrow", defaults.get("arrow", "neutral@5")))
    return Theme(**{**theme.__dict__, "text": text, "arrow": arrow})


def load_all(path: Path | None = None,
             swatch_path: Path | None = None) -> tuple[dict[str, Theme], str | None]:
    data = json.loads((path or palettes_path()).read_text())
    swatches = registry.load_swatches(swatch_path or swatches_path())
    themes = {name: _build(name, spec, data["defaults"], swatches)
              for name, spec in data.get("themes", {}).items()}
    default = data.get("default_theme")
    if default is not None and default not in themes:
        raise ThemeError(f"default_theme {default!r} is not defined")
    return themes, default


def load(name: str | None = None) -> Theme:
    themes, default = load_all()
    if not themes:
        raise ThemeError("no theme yet: add swatches from screenshots, then a theme "
                         "(see references/color-books.md)")
    key = name or default or next(iter(themes))
    if key not in themes:
        raise ThemeError(f"unknown theme {key!r}; choose from {sorted(themes)}")
    return themes[key]


# ------------------------------------------------------------------- audit

def _sim(color: str, mode: str) -> str:
    return color if mode == "normal" else cl.simulate_cvd(color, mode)


def min_pair_delta(colors: list[str], mode: str = "normal") -> tuple[float, str, str]:
    pairs = itertools.combinations(colors, 2)
    return min(((cl.delta_e(_sim(a, mode), _sim(b, mode)), a, b) for a, b in pairs))


def cvd_safe_count(theme: Theme) -> int:
    """Largest k such that the first k anchors stay >= MIN_DE_CVD apart under every CVD."""
    cycle, safe = theme.cycle, 1
    for k in range(2, len(cycle) + 1):
        if min(min_pair_delta(cycle[:k], m)[0] for m in cl.CVD_MATRICES) < MIN_DE_CVD:
            break
        safe = k
    return safe


def gray_safe_count(theme: Theme) -> int:
    """Largest k such that the first k series anchors all differ by >= MIN_GRAY_PAIR L*."""
    series, safe = [theme.anchors[r] for r in theme.series], 1
    for k in range(2, len(series) + 1):
        ls = [cl.lightness(c) for c in series[:k]]
        if min(abs(a - b) for a, b in itertools.combinations(ls, 2)) < MIN_GRAY_PAIR:
            break
        safe = k
    return safe


def series_stats(theme: Theme) -> dict[str, int]:
    return {"cvd_safe": cvd_safe_count(theme), "gray_safe": gray_safe_count(theme)}


def _audit_ramp(theme: Theme, role: str, check) -> None:
    ls = [cl.lightness(c) for c in theme.ramps[role]]
    kind = "book" if all(theme.ramp_codes[role]) else "derived"
    for i in range(len(ls) - 1):
        gap = ls[i] - ls[i + 1]
        check(gap >= MIN_RAMP_STEP, "ERROR",
              f"{role} {kind} ramp steps {i + 1}->{i + 2}: L* gap {gap:.1f} < {MIN_RAMP_STEP} "
              "(steps must go light -> dark and stay distinguishable)")
        check(gap < MIN_RAMP_STEP or gap >= GOOD_RAMP_STEP, "WARN",
              f"{role} ramp steps {i + 1}->{i + 2}: L* gap {gap:.1f}, hard to tell apart in print")
    chromatic = [h for _, c, h in map(cl.to_oklch, theme.ramps[role]) if c > 0.04]
    if kind == "book" and len(chromatic) > 1:
        spread = max(cl.hue_distance(a, b) for a, b in itertools.combinations(chromatic, 2))
        check(spread <= MAX_RAMP_HUE_SPREAD, "WARN",
              f"{role} book ramp hue spread {spread:.0f} deg; it may not read as one hue")


def _audit_anchors(theme: Theme, check) -> None:
    a = theme.anchors
    for role in ("ours", "base1", "base2", "base3"):
        r = cl.contrast_ratio(a[role])
        check(r >= MIN_LINE_CONTRAST, "ERROR",
              f"{role} ({theme.codes[role]}) contrast {r:.2f} < {MIN_LINE_CONTRAST}")
    for role in [r for r in ("base4", "base5", "neutral") if r in a]:
        r = cl.contrast_ratio(a[role])
        check(r >= MIN_ANY_CONTRAST, "ERROR",
              f"{role} ({theme.codes[role]}) contrast {r:.2f} < {MIN_ANY_CONTRAST}")
        check(r >= MIN_LINE_CONTRAST, "WARN",
              f"{role} contrast {r:.2f}: use as a fill with dark edge or a >=1.5pt line")
    d, x, y = min_pair_delta(theme.cycle)
    check(d >= MIN_DE_NORMAL, "ERROR", f"normal vision: {x} vs {y} dE={d:.1f} < {MIN_DE_NORMAL}")
    for mode in cl.CVD_MATRICES:
        d, x, y = min_pair_delta(theme.cycle[:CVD_CORE], mode)
        check(d >= MIN_DE_CVD, "ERROR", f"{mode}: {x} vs {y} dE={d:.1f} < {MIN_DE_CVD}")
    ours_l = cl.lightness(a["ours"])
    for role in ("base1", "base2", "base3"):
        gap = abs(ours_l - cl.lightness(a[role]))
        check(gap >= MIN_GRAY_GAP, "ERROR",
              f"grayscale: ours vs {role} L* gap {gap:.1f} < {MIN_GRAY_GAP}")


def audit(theme: Theme) -> list[tuple[str, str]]:
    """Return [(level, message)], level in ERROR/WARN/INFO."""
    issues: list[tuple[str, str]] = []

    def check(ok: bool, level: str, msg: str) -> None:
        if not ok:
            issues.append((level, msg))

    _audit_anchors(theme, check)
    for role in theme.hues:
        _audit_ramp(theme, role, check)
    for role in ("gain", "drop", "link"):
        r = cl.contrast_ratio(theme.text[role])
        check(r >= MIN_TEXT_CONTRAST, "ERROR", f"{role} = {theme.text_refs[role]}: text contrast "
                                               f"{r:.2f} < {MIN_TEXT_CONTRAST}; pick a darker step")
    hl = cl.lightness(theme.text["highlight"])
    check(hl >= MIN_HIGHLIGHT_L, "ERROR", f"highlight = {theme.text_refs['highlight']}: "
                                          f"L*={hl:.1f} < {MIN_HIGHLIGHT_L}; pick a lighter step")
    for side in (theme.diverging[:3], theme.diverging[2:][::-1]):
        ls = [cl.lightness(c) for c in side]
        check(ls == sorted(ls), "ERROR", f"diverging side {side} is not monotonic in L*")
    imbalance = abs(cl.lightness(theme.diverging[0]) - cl.lightness(theme.diverging[-1]))
    check(imbalance <= MAX_DIV_IMBALANCE, "WARN",
          f"diverging ends differ by {imbalance:.1f} L*; one side will look heavier")
    d, x, y = min_pair_delta([v["fill"] for v in theme.diagram.values()])
    check(d >= MIN_DE_FILLS, "WARN", f"diagram fills {x} vs {y} dE={d:.1f} < {MIN_DE_FILLS}")

    stats = series_stats(theme)
    issues.append(("INFO", f"CVD-safe series count: {stats['cvd_safe']} "
                           "(beyond this, add marker / linestyle / hatch)"))
    issues.append(("INFO", f"grayscale-safe series count: {stats['gray_safe']} "
                           "(for B/W print, use style(i, redundant=True))"))
    return issues
