# Color books, swatches and themes

All paper colors come from one spot-color book, typically a PANTONE® book. Their sRGB values come only from data the user supplies and is licensed to use: color book files they obtained under their own license, exports or screenshots from their own Pantone Connect account, or a pantone-cli index they built from their own licensed account. This skill bundles no color book data. You never download, fetch or scrape it for the user, and you never point them to prebuilt or shared copies (see [licensing](../SKILL.md#licensing-and-trademarks)). Routes, in order of preference:

| Route | Use when | Command |
|---|---|---|
| 0. Local color books + matching | the user has licensed color book files (`.acb` / `.aco` / `.ase`) | `swatch library add <file>`, `swatch match`, `swatch add --from-library` |
| 0b. pantone-cli index + matching | the user built an index from their own licensed Pantone Connect account with [pantone-cli](https://github.com/malhashemi/pantone-cli) | `swatch library add --from-pantone-cli`, then as route 0 |
| 1. Collection export (`.ase`) | the user saved the colors into a Connect collection and exported it | `swatch import <file.ase>` |
| 2. Screenshots or pasted text | a few colors, or ASE export is unavailable | `swatch sample` + `swatch add` |

## Where things live

Everything the user adds lives in the **data folder**, `$PAPER_COLORS_HOME` (default `~/.paper-colors/`), never inside the skill, so updating the skill keeps it. `python3 $S init` creates it (`--from <old skill dir>` copies an older install's `pantone/` data and `palettes.json`); `python3 $S where` prints the paths in use.

| Path (in the data folder) | Holds |
|---|---|
| `inbox/` | screenshots and files waiting to be read (the user drops them here, or gives another path) |
| `swatches.json` | registry: book code → name, sRGB hex, how it was read, screenshot |
| `palettes.json` | themes: which book code anchors each hue, ramps, text roles (until `init`, the skill's empty template is read) |
| `screenshots/` | registered screenshots, kept as provenance |
| `imports/` | imported `.ase` files, kept as provenance |
| `libraries/` | indexed books (`<book>.json`: colors, use and medium, Connect harmonies) and color book originals (`source/`); a local matching index only |
| `verify/` | Pantone Connect checklists (`*.tsv`); results are recorded in `swatches.json` |

## Choosing the book

The same color maps to different codes in different books, so each paper uses **one** book. `swatch library list` shows each indexed book's intended use, physical medium and the share of its colors outside sRGB (from the book's name, or from pantone-cli's book metadata).

- A paper is read on screens and as a PDF, so the colors that matter are the sRGB ones. Prefer a book with a small share outside sRGB, and avoid anchors flagged `outside sRGB`: what readers see is a clipped approximation.
- Without another reason, use **Solid Coated** (the usual graphic-design book), or **Solid Uncoated** for a calmer, lower-chroma look. Use **TCX / TPG** when the user's palette came from fashion or product color pages (codes like `00-0001 TCX`).
- Avoid **Metallics** and **Pastels & Neons**: their sheen and fluorescence cannot be shown on screen.
- Tell the user which book you chose and why, in one line.

## Reading a Delta E00

Every match reports CIEDE2000 (Delta E00) against the book's Lab values (D50, as color books publish them, adapted to D65 with Bradford). Report the number with the code, and read it as:

| Delta E00 | Meaning | Grade used by `match` / `verify` |
|---|---|---|
| < 1 | not perceptible | `match` / `ok` |
| 1–2 | perceptible on close inspection | `match` / `ok` |
| 2–4 | noticeable | `close` / `check` |
| 4–10 | clearly different | `close` / `check` up to 5, then `far` / `mismatch` |
| ≥ 10 | no good match in this book: say so | `far` / `mismatch` |

Matching is an approximation: Pantone Connect may use its own matching and substrate assumptions. Say so when you report matches, and for production-critical color recommend checking a physical guide. This skill is not affiliated with or endorsed by Pantone LLC; PANTONE® is a registered trademark of Pantone LLC.

## Route 0: color books + matching screenshots to them

Color books are full color libraries as files (Photoshop / Illustrator color books, Pantone Connect exports) that the user obtained under their own license. With them, a screenshot only has to say *roughly* which color; the registered value comes from the book.

1. **Index each book once**: `python3 $S swatch library add <file> [--name "<book name>"]`. The format is detected from the file's signature (`.acb` Adobe Color Book, `.aco` Photoshop swatches, `.ase`). Lab values (D50) are kept unclipped for matching; colors outside sRGB are counted and flagged; CMYK / Gray-only entries are skipped. An unknown format errors out with its first bytes — ask the user for that file as a sample and add a reader in `scripts/colorbooks.py`. `swatch library list` shows what is indexed.
   - **From pantone-cli** instead: `python3 $S swatch library books` lists the books of the user's index (found as pantone-cli finds it: `--index`, `$PANTONE_INDEX`, `./pantone-match-index.json`, `~/.pantone-cli/`), then `python3 $S swatch library add --from-pantone-cli --books <id>,<id>` indexes them. The index is read in place, not copied. If there is none, say that pantone-cli can build one from their own Pantone Connect account (`pantone-cli export` then `pantone-cli index`, where their Pantone license allows API access), and leave that to them. Do not suggest a prebuilt or shared index.
2. **Agree on one book per paper** ([choosing the book](#choosing-the-book)) and pass it as `--library` from here on, so one paper does not mix libraries.
3. **Match** each palette entry: `uv run --with pillow python3 $S swatch match "<code>=<#hex>" ... --library "<book>"` (or a bare code, `#hex`, or a screenshot).
   - **Code first.** A code is looked up exactly in the books; a bare code from a palette page gets its suffix completed (`00-0004` → TCX, then TPG; `0001` → C, then U).
   - **Else approximate, lighter by default.** If the code is in no book, the entry's color (`=#hex`, sampled from the screenshot) is matched by CIEDE2000, and a candidate *lighter* than the target wins if it is at most dE 2 worse than the nearest one (and ≤ 5 overall); otherwise the nearest wins. `--prefer nearest|darker` changes this. The output marks the choice with `*` and says why.
   - A screenshot is converted from its ICC profile to sRGB, its dominant non-background colors are listed with bounding boxes (`--colors N`), and each gets the `--top` nearest book colors by CIEDE2000, graded `match` (dE ≤ 2), `close` (≤ 5) or `far` (> 5).
   - Show the user the candidates. `far` means a color-shifted screenshot or no counterpart in that book: do not pick it silently. `outside sRGB` means the color cannot be shown exactly on screens or in PDFs; its hex is the clipped approximation.
4. **Register** the chosen codes with their book values: re-run the match with `--register` (skips `far` choices), or `python3 $S swatch add "<code>" --from-library --library "<book>"` per code (method `library`; never overwrites a different existing value).
5. **Verify against Pantone Connect** (the user's own account) — book files and indexes can be older editions, so book values are provisional until checked:
   - `python3 $S swatch verify` writes `verify/<date>-registered.tsv` (data folder) listing every registered swatch not yet verified `ok`, with our hex and an empty `connect_hex` column. (`swatch verify CODE ...` or `--library <book> --sample K` builds a checklist for other codes.)
   - The user looks each code up in Pantone Connect and fills in the HEX shown there (or pastes `CODE  #HEX` lines).
   - `python3 $S swatch verify --values <file>` reports dE per code: `ok` (≤ 2), `check` (≤ 5), `mismatch` (> 5), and writes a `verified` record into each registered swatch. Exit 1 if anything is not `ok`.
   - For `check` / `mismatch`, and for out-of-sRGB colors (Connect applies its own screen mapping, which beats our per-channel clipping), re-run with `--adopt`: the registered hex becomes Connect's, the book value is kept as `book_hex`.

*Done when* every color the user picked is registered from the agreed book, verified `ok` against Connect or adopted from it, and any `far` choice was confirmed by the user.

## Route 1: importing a Pantone Connect collection

In Pantone Connect: add the paper's colors to one collection (anchors, plus every shade of any all-book ramp), export it as **Adobe Swatch Exchange (.ase)**, preferably with RGB/HEX values, and put the file in the data folder's `inbox/` or give its path.

1. `python3 $S swatch import <file.ase> --dry-run` and show the user the table.
2. `python3 $S swatch import <file.ase>`; the file is copied to `imports/` in the data folder.
   - RGB and Gray swatches are taken as sRGB; LAB swatches are converted from D50 (Pantone's default) with Bradford adaptation; CMYK swatches are skipped (device-dependent) — ask for an RGB/HEX or LAB export instead.
   - The book code is parsed from the swatch name (`PANTONE 00-0001 TCX Test Blue` → `00-0001 TCX`).
   - Existing entries are never overwritten: the same color again is `unchanged`; a different color under a known code is a `conflict` (exit 1) for the user to resolve.

*Done when* the import reports no conflicts and every code the user wanted appears in `swatch list`.

## Route 2: registering swatches from screenshots or pasted values

If the user pastes codes and HEX values as text, register each with `swatch add "<code>" --name "<name>" --hex <HEX>` and skip the steps below.

For every image in `swatch inbox` (or every path the user gives):

1. **Read it** (open the image). Note the code exactly as printed (`00-0001 TCX`, `0001 C`, `P 000-1 C`), the color name, and the HEX if the page shows one.
2. **Sample it**: `uv run --with pillow python3 $S swatch sample <image>`. It converts the screenshot from its embedded ICC profile (often Display P3 on macOS) to sRGB and lists the largest flat color areas with bounding boxes. Pick the row whose box is the swatch you saw; for a page with several swatches, re-run with `--box x0,y0,x1,y1` around one.
3. **Register**: `python3 $S swatch add "<code>" --name "<name>" --hex <page HEX> --sampled <sampled hex> --screenshot <image>`.
   - With both readings, `add` rejects them if they differ by more than ΔE 3 — then the screenshot was color-shifted (night mode, True Tone, a non-color-managed viewer) or the wrong area was sampled. Tell the user; do not force it.
   - With no HEX on the page, pass only `--sampled`; the entry is marked `sampled`.
   - The screenshot moves to `screenshots/` in the data folder.

*Done when* `swatch inbox` is empty and every code the user asked for appears in `swatch list`.

## Building a theme

A theme in `palettes.json` needs hues `ours`, `base1`, `base2`, `base3`, `neutral` (optionally `base4`, `base5`), each anchored on a registered book code:

```json
"my-paper": {
  "description": "one line on the look",
  "hues": {
    "ours":    "00-0001 TCX",
    "base1":   {"anchor": "00-0002 TCX",
                "ramp": ["<lightest code>", "<code>", "00-0002 TCX", "<code>", "<darkest code>"]},
    "base2":   "...", "base3": "...", "neutral": "00-0003 TCX"
  },
  "text": {"highlight": "ours@1", "gain": "base2@5", "drop": "base1@5", "link": "ours@5"},
  "diverging": ["base1", "ours"]
}
```

- **Ramps** (5 steps by default, `"steps": N` to change; step 1 lightest): a hue given as a bare code gets a **derived** ramp — same OKLab hue as the anchor, lightness evenly spaced from L* 92 to 28, the anchor kept exactly at the nearest step. A hue given with `"ramp": [...]` uses **only book colors** listed light → dark, which must include the anchor. Both kinds can be mixed in one theme; `show` marks which is which.
- **`text`** picks highlight / gain / drop / link from ramp steps (`role@step`), so text highlighting stays inside the palette. Highlight needs a very light step (L* ≥ 90), the others dark steps (≥ 4.5:1 contrast).
- Assigning anchors: the most saturated, darkest-reading color → `ours`; hues far apart on the color wheel for `base1`–`base3`, not a red–green pair; a gray from the book → `neutral`.
- **Proposing baselines from `ours`**: `python3 $S swatch harmony "<ours code>" --library "<book>"` lists analogous, complementary, split-complementary, triadic, tetradic and monochromatic candidates in that book. They are Pantone Connect's own harmonies when the book came from a pantone-cli index (`[connect]`), otherwise the anchor's OKLCh hue rotated and snapped to the nearest book color (`[computed]`, with the dE of the snap). Triadic and tetradic sets suit `base1`–`base3`; analogous ones are too close for distinct methods but suit related variants; monochromatic ones suit an explicit ramp. Offer two or three sets to the user, not all of them.

Then `python3 $S audit my-paper`. Typical fixes: swap which book color anchors which role, choose a darker book color for a pale baseline, reorder baselines so the colorblind-closest pair is not among the first four. For an explicit ramp, a step too close to its neighbour (< 8 L*) means picking another shade from the book. *Done when* audit prints PASS; then set `"default_theme"` if this is the main palette and open the exported `paper-colors-swatches.svg` with the user.
