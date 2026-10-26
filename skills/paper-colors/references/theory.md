# Why these rules, and how to change the palette

## Audit thresholds

The numbers live as constants at the top of `scripts/themes.py`; this table explains them.

| Check | Threshold | Reason |
|---|---|---|
| contrast vs white, anchors of ours / base1-3 | ≥ 3:1 | WCAG 1.4.11 for graphical objects; thin lines must be visible on paper and projectors |
| contrast, base4 / base5 / neutral | ≥ 2:1 (warn < 3) | usable as filled bars with dark edges |
| contrast, gain / drop / link | ≥ 4.5:1 | WCAG AA body text |
| CIEDE2000 between any two cycle colors | ≥ 15 | clearly different for normal vision, also as small markers |
| CIEDE2000 under protan / deutan / tritan, first 4 | ≥ 10 | ~8% of men have a red-green deficiency; at least 4 series must survive |
| L* gap ours vs base1-3 | ≥ 10 | grayscale print: ours is still found first |
| grayscale pair (for `GRAY_SAFE`) | L* gap ≥ 8 | two series printed in B/W look different |
| highlight L* | ≥ 90 | it is a background under black text |
| sequential / diverging | L* monotonic per side | perceived order = data order |
| diverging ends | L* gap ≤ 15 (warn) | neither side looks heavier |
| diagram fills | ΔE ≥ 4 (warn) | box types stay distinct |
| neighbouring ramp steps | L* gap ≥ 8 (warn < 11) | ordered levels stay distinguishable, also in print |
| explicit book ramp hue spread | ≤ 30° OKLCh (warn) | the steps read as one hue |

Two counts are exported as `CVD_SAFE` and `GRAY_SAFE`:

- `CVD_SAFE`: the largest prefix of the cycle (ours, base1, …) that keeps ΔE ≥ 10 under all three simulations. `style(i)` adds shapes from that index on.
- `GRAY_SAFE`: the largest prefix whose colors all differ by ≥ 8 L*, i.e. what a B/W printout separates by lightness alone. It is 2–3 for every theme: hue-distinct palettes cannot also be lightness-distinct for many series. That is why grayscale figures need `style(i, redundant=True)`.

## Linter limits

`lint` reads source text: hex / `rgb()` literals, xcolor models (`[HTML]`, `{rgb}`, `{RGB}`), xcolor / TikZ / matplotlib / SVG / draw.io named colors, matplotlib format strings, and rainbow colormaps. It does not see colors computed at runtime (variables, loops, seaborn palettes by name other than rainbow ones) or colors inside PDF / PNG / PPTX files. Hence the grayscale look at each final figure in workflow step 5.

## Color science used (`scripts/colorlib.py`)

- **CIEDE2000** on CIELAB (D65) — the standard perceptual difference; verified against Sharma et al. (2005) reference pairs in the tests.
- **CVD simulation**: Machado, Oliveira & Fernandes (2009), severity 1.0, in linear RGB.
- **Grayscale**: relative luminance (Rec. 709 weights), which is what a B/W printer keeps.
- **Tints** mix in gamma-encoded sRGB, matching xcolor, so `tint(c, .2)` in Python is the same color as `c!20` in LaTeX and in the linter.

## Derived ramps (`scripts/ramps.py`)

A hue given as a bare book code gets a ramp built in **OKLab / OKLCh**, whose hue stays constant as lightness changes (in CIELAB, blues drift to purple when lightened):

1. Target CIE L* values are evenly spaced from 92 (lightest, still visible on white) to 28 (darkest, still not black).
2. The anchor takes the slot nearest its own L*; the other steps are re-spaced evenly between it and the two ends, so the book color itself is always one of the steps, unchanged.
3. Each step keeps the anchor's OKLab hue; chroma tapers toward the ends (30% of the anchor's at the light end, 75% at the dark end) and is reduced further only if the color would leave sRGB.

Explicit book ramps are not modified, only audited (monotonic, step gaps, hue spread).

## Adding or editing a theme

See [color-books.md](color-books.md#building-a-theme) for the schema and the screenshot workflow. Tests run against `tests/fixtures/` (invented codes), never the real registry: `uv run --with pillow python -m unittest discover -s tests`.
