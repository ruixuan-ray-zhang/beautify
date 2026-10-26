# beautify

Agent skills that make research artifacts look good: papers, figures, diagrams and tables.
They work with Claude Code, Codex, Cursor and other agents that read `SKILL.md` skills.

| Skill | What it does |
|---|---|
| [`paper-colors`](skills/paper-colors/SKILL.md) | One color theme per paper, taken from a spot-color book you are licensed to use (such as a PANTONE® book). It gives roles (ours, baselines, neutral), light-to-dark ramps for ordered conditions, harmonies to propose hues, exports for matplotlib / pgfplots / LaTeX / diagrams, and a lint that finds off-palette colors. Contrast, colorblind and grayscale checks are built in. |

## Install

With the [skills](https://skills.sh) CLI:

```bash
npx skills add ruixuan-ray-zhang/beautify
```

Or by hand: copy or symlink `skills/paper-colors` into your agent's skills folder (for Claude Code,
`~/.claude/skills/paper-colors`).

`paper-colors` needs only Python 3.10+. Screenshot sampling also needs Pillow
(`uv run --with pillow ...`). After installing, the agent runs `paper_colors.py init` once. That
creates your data folder, `~/.paper-colors/` (change it with `PAPER_COLORS_HOME`). Your swatches, themes
and color books stay there, so updating the skill never touches them. To move data from an older
copy of the skill, run `paper_colors.py init --from <old skill folder>`.

## Works well with

These are separate projects by other authors. They are **not included** in this repository. Install
them from their own repositories and follow their licenses.

- [figures4papers](https://github.com/ChenLiu-1996/figures4papers) by Chen Liu: publication-ready
  matplotlib figure demos, plus a `scientific-figure-making` skill for fonts, layout and export
  (CC BY-NC 4.0). If both are installed, `paper-colors` handles the colors and that skill handles the
  rest of the figure style.
- [pantone-cli](https://github.com/malhashemi/pantone-cli) by malhashemi: offline color-book matching
  (MIT). `paper-colors` can read an index that you build with it. See [Color data](#color-data).

## Color data

This repository contains **no color book data**: no color books, no code-to-color tables, no
indexes. The tests use invented codes and synthetic colors only. `paper-colors` works with data
**you supply and are licensed to use**, and it keeps that data on your machine:

- color book files (`.acb` / `.aco` / `.ase`) you obtained under your own license, or a
  collection you export from your own Pantone Connect account;
- an offline index you build from your own Pantone Connect account with
  [pantone-cli](https://github.com/malhashemi/pantone-cli) (`pantone-cli export`, then
  `pantone-cli index`), where your license allows it. `paper_colors.py swatch library add
  --from-pantone-cli` reads it in place;
- screenshots or HEX values from color pages in your own account.

Do not commit color books, indexes or your data folder to a public repository. A paper's exported
files carry only the handful of colors that paper uses.

Matching uses CIEDE2000 against the book's Lab values. It is an approximation and does not replace
Pantone Connect, physical Pantone guides or Pantone production guidance.

## Trademarks

This project is independent. It is not affiliated with, sponsored by or endorsed by Pantone LLC.
PANTONE® is a registered trademark of Pantone LLC. Other trademarks belong to their owners. Book
and product names appear only to identify the files a user brings.

Rights holders with a concern about this repository can open an issue. I will respond promptly.

## Development

```bash
uv run --with pytest --with pillow python -m pytest -q skills/paper-colors/tests
```

## License

[MIT](LICENSE). The license covers the code and documentation in this repository. It does not cover
any color book data you use with it.
