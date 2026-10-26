---
name: paper-colors
description: >-
  Paper color (配色) palette built from spot-color book colors (such as
  PANTONE®), with light-to-dark ramps and checks. Use when registering color
  book colors (.acb/.aco/.ase files, a self-built pantone-cli index, matching
  screenshots or HEX to a book, collection exports), proposing harmonious
  hues for a palette, choosing or
  applying colors for a paper figure (matplotlib, pgfplots), mapping ordered
  conditions (model size, strength) to shades, coloring boxes and arrows in a
  method diagram (TikZ, draw.io, PowerPoint, Figma), coloring LaTeX tables,
  links or highlighted text, or checking a paper for off-palette colors. Also
  when scientific-figure-making needs colors: this skill owns its palette.
license: MIT
---

# Paper colors

One paper = one **theme** of colors from one color book (typically a PANTONE® book the user is licensed to use). Every color in every figure, diagram, table and text highlight is an anchor or ramp step of that theme, optionally with transparency. Sources of truth live in the user's **data folder** (`$PAPER_COLORS_HOME`, default `~/.paper-colors/`, never inside this skill): `swatches.json` (book code → sRGB) and `palettes.json` (themes). The skill ships no color book data. Tools: `scripts/paper_colors.py` (stdlib Python; screenshot sampling also needs Pillow via `uv run --with pillow`). Add `--json` to `match`, `harmony`, `swatch list` and `library list` when you parse the output.

```bash
S=<this skill's folder>/scripts/paper_colors.py
python3 $S init [--from <old skill dir>] # create the data folder (once); `where` prints it
python3 $S swatch library add <book>    # index a color book (.acb / .aco / .ase), once
python3 $S swatch library add --from-pantone-cli [--books ID,ID]  # or a self-built pantone-cli index
python3 $S swatch library list          # books: use, medium, share outside sRGB
python3 $S swatch match <shot|#hex|code> --library <book>   # nearest book colors
python3 $S swatch harmony <code> --library <book>   # candidate hues around an anchor
python3 $S swatch import <file.ase>     # a whole collection export
python3 $S swatch inbox                 # screenshots waiting in the data folder's inbox/
python3 $S list | show [theme] | audit   # themes, their ramps, the quality gate
python3 $S export <theme> --out <dir>    # files for the paper project
python3 $S lint <paper-dir>              # off-palette colors; exit 1 if any
```

## Roles and ramps

| Role | Meaning | LaTeX | Python |
|---|---|---|---|
| `ours` | the proposed method; most salient hue | `cOurs` | `C["ours"]` |
| `base1`..`base5` | baselines, in order of importance (base4/5 optional) | `cBase1`.. | `C["base1"]` / `style(1)` |
| `neutral` | reference / oracle / background (a gray from the book) | `cNeutral` | `C["neutral"]` |
| step *k* of a hue | ordered level, 1 = lightest … 5 = darkest | `cOursS1`..`cOursS5` | `RAMP["ours"][k-1]`, `ramp("ours", n)` |
| `highlight`, `gain`, `drop`, `link` | text marking, picked from ramp steps | `cHighlight`, `\gain{}`, … | `C["highlight"]` … |

Each hue has a 5-step ramp, light → dark: **derived** from its anchor (same hue, even lightness steps) or an **explicit list of book colors**. Ordered experimental variables map onto one hue's ramp: model size small → large, strength weak → strong, training steps few → many = light → dark (`ramp("ours", 3)` for three levels). Diagram fills are step 1; sequential colormap = the `ours` ramp; diverging = `base1` ramp – neutral – `ours` ramp (configurable).

## Workflow

1. **Collect the colors.** Run `init` once if `where` shows the bundled template. Agree on one book for the paper ([choosing the book](references/color-books.md#choosing-the-book)). With the user's color book files or pantone-cli index indexed, match their screenshots or codes against the book (`swatch match`, then `swatch add --from-library`, then `swatch verify` against Pantone Connect); otherwise a Pantone Connect collection export (`swatch import <file.ase>`), screenshots or pasted HEX (`swatch add`). Follow [licensing and trademarks](#licensing-and-trademarks). When you report a match, give its Delta E00 and read it with the [table](references/color-books.md#reading-a-delta-e00), and say once that matching is an approximation. Follow [references/color-books.md](references/color-books.md). *Done when* every requested code is in `swatch list`.
2. **Fix the theme.** If the project already has `paper-colors.sty` / `paper_colors.py`, its header names the theme — use it. Otherwise build one from registered codes, using `swatch harmony` on the `ours` anchor to propose baselines ([references/color-books.md](references/color-books.md#building-a-theme)). *Done when* `audit <theme>` prints PASS and the user agreed on it.
3. **Assign roles.** Write a method → role map (Ours → `ours`, strongest baseline → `base1`, …) and, for each ordered variable, which hue's ramp carries it and which step each level gets. Record both in the paper's notes (e.g. `figures/README.md`). *Done when* every method and every level appearing in any figure or table has exactly one color.
4. **Export into the project.** `export <theme> --out <dir>` next to the figure scripts and next to `main.tex`; add `\usepackage{paper-colors}`. *Done when* figure code imports `paper_colors` and the paper compiles.
5. **Apply per medium** — open only the file you need:
   - matplotlib / pgfplots data figures → [references/figures.md](references/figures.md)
   - method / architecture diagrams (TikZ, draw.io, PPT, Figma) → [references/diagrams.md](references/diagrams.md)
   - LaTeX tables, colored text, links, captions → [references/latex.md](references/latex.md)

   *Done when* every figure, diagram and table you touched takes its colors only from roles / ramp steps, using the step-3 map.
6. **Verify.** Run `lint <paper-dir>` and fix every finding or tell the user why it stays; lint cannot see colors computed at runtime, so also open each changed figure once in grayscale. *Done when* lint exits 0 (or every remaining finding is justified) and in each grayscale figure ours is found first and every series and level is still told apart.

## Rules (all media)

- **Only theme colors.** Use role names and ramp steps (`C["base2"]`, `RAMP["ours"][2]`, `cBase2`, `cOursS3`), never a fresh hex. Transparency is allowed for overlaps and bands (`alpha=`, `cOurs!30`): on white it equals a tint, which the linter accepts.
- **One method, one hue; one level, one step** — across the whole paper: plots, diagrams, table shading and caption swatches agree.
- **Ordered levels go light → dark within one hue**, never across hues; distinct methods get distinct hues.
- **Ours is the most salient mark**: its anchor color, the heaviest line or edge, drawn on top, first in the legend.
- **Past the safe series count, add shape.** Beyond `CVD_SAFE` series (or `GRAY_SAFE` for black-and-white print) distinguish series also by marker / dash / hatch; `style(i)` does this.
- **To change the palette**, register new screenshots and edit the theme ([references/color-books.md](references/color-books.md)); exported files are regenerated, not edited. Thresholds and color science: [references/theory.md](references/theory.md).

## Licensing and trademarks

- **Use only color data the user supplies and is licensed to use**: their own color book files, collection exports or screenshots from their own account, or a pantone-cli index they built from their own licensed account. Never download, fetch or scrape color book data for them, never suggest prebuilt or shared indexes or color book files, and never guess a book code or its HEX from memory.
- **Data stays in the user's data folder.** Do not copy book files, indexes or registries into a repository; a paper's exported files carry only the few colors it uses.
- **Refer to the brand only to name the user's data** ("PANTONE Solid Coated", "the user's PANTONE book"). Do not put PANTONE in names of files, packages, macros or figure titles you create, and do not imply that a palette is approved by Pantone.
- This skill is not affiliated with or endorsed by Pantone LLC. PANTONE® is a registered trademark of Pantone LLC.
