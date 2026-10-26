"""Pure-stdlib color math: sRGB, CIELAB, CIEDE2000, contrast, CVD simulation.

Mixing (tint/shade) is done in gamma-encoded sRGB on purpose: that is what
xcolor's ``name!20`` does, so ``tint(c, 0.2)`` here equals ``c!20`` in LaTeX.
"""

from __future__ import annotations

import math
import re

HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")

# Machado, Oliveira & Fernandes (2009), severity 1.0, applied in linear RGB.
CVD_MATRICES = {
    "protan": ((0.152286, 1.052583, -0.204868),
               (0.114503, 0.786281, 0.099216),
               (-0.003882, -0.048116, 1.051998)),
    "deutan": ((0.367322, 0.860646, -0.227968),
               (0.280085, 0.672501, 0.047413),
               (-0.011820, 0.042940, 0.968881)),
    "tritan": ((1.255528, -0.076749, -0.178779),
               (-0.078411, 0.930809, 0.147602),
               (0.004733, 0.691367, 0.303900)),
}

_WHITE_XYZ = (0.95047, 1.0, 1.08883)  # D65


def parse_hex(value: str) -> tuple[float, float, float]:
    """'#RRGGBB' -> sRGB floats in [0, 1]. Raises ValueError on bad input."""
    match = HEX_RE.match(value.strip())
    if not match:
        raise ValueError(f"not a #RRGGBB color: {value!r}")
    digits = match.group(1)
    return tuple(int(digits[i:i + 2], 16) / 255 for i in (0, 2, 4))


def to_hex(rgb: tuple[float, float, float]) -> str:
    clipped = (min(1.0, max(0.0, c)) for c in rgb)
    return "#" + "".join(f"{round(c * 255):02X}" for c in clipped)


def _to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _to_gamma(c: float) -> float:
    c = min(1.0, max(0.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def relative_luminance(hex_color: str) -> float:
    r, g, b = (_to_linear(c) for c in parse_hex(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str = "#FFFFFF") -> float:
    """WCAG 2.x contrast ratio, 1.0 .. 21.0."""
    hi, lo = sorted((relative_luminance(fg), relative_luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def to_lab(hex_color: str) -> tuple[float, float, float]:
    r, g, b = (_to_linear(c) for c in parse_hex(hex_color))
    xyz = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b,
           0.2126729 * r + 0.7151522 * g + 0.0721750 * b,
           0.0193339 * r + 0.1191920 * g + 0.9503041 * b)

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    fx, fy, fz = (f(v / w) for v, w in zip(xyz, _WHITE_XYZ))
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def lightness(hex_color: str) -> float:
    """CIE L* (0 black .. 100 white): what survives grayscale printing."""
    return to_lab(hex_color)[0]


def delta_e_lab(lab1, lab2) -> float:
    """CIEDE2000 between two Lab triples."""
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2
    c_bar = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    g = 0.5 * (1 - math.sqrt(c_bar ** 7 / (c_bar ** 7 + 25 ** 7)))
    a1p, a2p = a1 * (1 + g), a2 * (1 + g)
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if c1p else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if c2p else 0.0

    dlp = l2 - l1
    dcp = c2p - c1p
    if c1p * c2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360
    else:
        dhp = h2p - h1p + 360
    dhp_big = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp / 2))

    lp_bar = (l1 + l2) / 2
    cp_bar = (c1p + c2p) / 2
    if c1p * c2p == 0:
        hp_bar = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hp_bar = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hp_bar = (h1p + h2p + 360) / 2
    else:
        hp_bar = (h1p + h2p - 360) / 2

    t = (1 - 0.17 * math.cos(math.radians(hp_bar - 30))
         + 0.24 * math.cos(math.radians(2 * hp_bar))
         + 0.32 * math.cos(math.radians(3 * hp_bar + 6))
         - 0.20 * math.cos(math.radians(4 * hp_bar - 63)))
    d_theta = 30 * math.exp(-(((hp_bar - 275) / 25) ** 2))
    r_c = 2 * math.sqrt(cp_bar ** 7 / (cp_bar ** 7 + 25 ** 7))
    s_l = 1 + 0.015 * (lp_bar - 50) ** 2 / math.sqrt(20 + (lp_bar - 50) ** 2)
    s_c = 1 + 0.045 * cp_bar
    s_h = 1 + 0.015 * cp_bar * t
    r_t = -math.sin(math.radians(2 * d_theta)) * r_c

    return math.sqrt((dlp / s_l) ** 2 + (dcp / s_c) ** 2 + (dhp_big / s_h) ** 2
                     + r_t * (dcp / s_c) * (dhp_big / s_h))


def delta_e(hex1: str, hex2: str) -> float:
    return delta_e_lab(to_lab(hex1), to_lab(hex2))


def simulate_cvd(hex_color: str, kind: str) -> str:
    """Full-severity dichromat simulation; kind in protan/deutan/tritan."""
    matrix = CVD_MATRICES[kind]
    lin = [_to_linear(c) for c in parse_hex(hex_color)]
    out = (sum(m * v for m, v in zip(row, lin)) for row in matrix)
    return to_hex(tuple(_to_gamma(c) for c in out))


def grayscale(hex_color: str) -> str:
    """Gray with the same luminance, i.e. what a B/W printer produces."""
    y = _to_gamma(relative_luminance(hex_color))
    return to_hex((y, y, y))


def mix(hex1: str, hex2: str, weight1: float) -> str:
    """sRGB mix, same as xcolor ``hex1!<weight1*100>!hex2``."""
    c1, c2 = parse_hex(hex1), parse_hex(hex2)
    return to_hex(tuple(weight1 * a + (1 - weight1) * b for a, b in zip(c1, c2)))


def tint(hex_color: str, amount: float) -> str:
    """Keep ``amount`` of the color, rest white. ``tint(c, .15)`` == xcolor ``c!15``."""
    return mix(hex_color, "#FFFFFF", amount)


def shade(hex_color: str, amount: float) -> str:
    """Keep ``amount`` of the color, rest black. ``shade(c, .7)`` == ``c!70!black``."""
    return mix(hex_color, "#000000", amount)


def nearest_tint(hex_color: str, base: str) -> tuple[float, float]:
    """Best ``tint(base, t)`` (t in 0.05..1) for hex_color -> (t, deltaE)."""
    best = (1.0, delta_e(hex_color, base))
    for step in range(5, 101):
        t = step / 100
        d = delta_e(hex_color, tint(base, t))
        if d < best[1]:
            best = (t, d)
    return best


# ---------------------------------------------------------------- OKLab / OKLCh
# Björn Ottosson's OKLab: hue stays put when lightness changes, so ramps built
# here do not drift (CIELAB blues turn purple when lightened).

def _linear_rgb(hex_color: str) -> tuple[float, float, float]:
    return tuple(_to_linear(c) for c in parse_hex(hex_color))


def to_oklch(hex_color: str) -> tuple[float, float, float]:
    r, g, b = _linear_rgb(hex_color)
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    lightness_ = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b2 = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return lightness_, math.hypot(a, b2), math.degrees(math.atan2(b2, a)) % 360


def oklch_to_linear(lightness_: float, chroma: float, hue: float) -> tuple[float, float, float]:
    a = chroma * math.cos(math.radians(hue))
    b = chroma * math.sin(math.radians(hue))
    l_ = (lightness_ + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (lightness_ - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (lightness_ - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
            -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
            -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_)


def in_gamut(linear: tuple[float, float, float], eps: float = 1e-6) -> bool:
    return all(-eps <= c <= 1 + eps for c in linear)


def oklch_to_hex(lightness_: float, chroma: float, hue: float) -> str:
    """OKLCh -> '#RRGGBB', reducing chroma (hue and lightness kept) until it fits sRGB."""
    lo, hi = 0.0, chroma
    if not in_gamut(oklch_to_linear(lightness_, chroma, hue)):
        for _ in range(30):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if in_gamut(oklch_to_linear(lightness_, mid, hue)) else (lo, mid)
        chroma = lo
    return to_hex(tuple(_to_gamma(c) for c in oklch_to_linear(lightness_, chroma, hue)))


def hue_distance(h1: float, h2: float) -> float:
    d = abs(h1 - h2) % 360
    return min(d, 360 - d)


# ------------------------------------------------------------ CIELAB, D50
# Pantone publishes L*a*b* for D50 (X-Rite: "default illuminant:observer D50:2"),
# so imported Lab values are adapted D50 -> D65 (Bradford) before going to sRGB.

_D50_WHITE = (0.96422, 1.0, 0.82521)
_BRADFORD_D50_TO_D65 = ((0.9555766, -0.0230393, 0.0631636),
                        (-0.0282895, 1.0099416, 0.0210077),
                        (0.0122982, -0.0204830, 1.3299098))
_BRADFORD_D65_TO_D50 = ((1.0478112, 0.0228866, -0.0501270),
                        (0.0295424, 0.9904844, -0.0170491),
                        (-0.0092345, 0.0150436, 0.7521316))
_XYZ_TO_SRGB = ((3.2404542, -1.5371385, -0.4985314),
                (-0.9692660, 1.8760108, 0.0415560),
                (0.0556434, -0.2040259, 1.0572252))
_SRGB_TO_XYZ = ((0.4124564, 0.3575761, 0.1804375),
                (0.2126729, 0.7151522, 0.0721750),
                (0.0193339, 0.1191920, 0.9503041))


def _matmul(m, v):
    return tuple(sum(a * b for a, b in zip(row, v)) for row in m)


def lab_d50_to_hex(lab: tuple[float, float, float]) -> tuple[str, bool]:
    """Lab (D50) -> ('#RRGGBB', in_gamut). Out-of-gamut colors are clipped per channel."""
    l, a, b = lab
    fy = (l + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200

    def finv(t: float) -> float:
        return t ** 3 if t ** 3 > 216 / 24389 else (116 * t - 16) * 27 / 24389

    xyz50 = tuple(finv(f) * w for f, w in zip((fx, fy, fz), _D50_WHITE))
    linear = _matmul(_XYZ_TO_SRGB, _matmul(_BRADFORD_D50_TO_D65, xyz50))
    return to_hex(tuple(_to_gamma(c) for c in linear)), in_gamut(linear, eps=1e-3)


def to_lab_d50(hex_color: str) -> tuple[float, float, float]:
    xyz50 = _matmul(_BRADFORD_D65_TO_D50, _matmul(_SRGB_TO_XYZ, _linear_rgb(hex_color)))

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    fx, fy, fz = (f(v / w) for v, w in zip(xyz50, _D50_WHITE))
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


_D65_WHITE = _WHITE_XYZ


def lab_d50_to_lab(lab: tuple[float, float, float]) -> tuple[float, float, float]:
    """Lab (D50, as in color books) -> the D65 Lab used by to_lab() / delta_e(), without
    clipping to sRGB, so out-of-gamut Pantone colors still compare correctly."""
    l, a, b = lab
    fy = (l + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200

    def finv(t: float) -> float:
        return t ** 3 if t ** 3 > 216 / 24389 else (116 * t - 16) * 27 / 24389

    xyz65 = _matmul(_BRADFORD_D50_TO_D65,
                    tuple(finv(f) * w for f, w in zip((fx, fy, fz), _D50_WHITE)))

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    gx, gy, gz = (f(v / w) for v, w in zip(xyz65, _D65_WHITE))
    return (116 * gy - 16, 500 * (gx - gy), 200 * (gy - gz))
