# LaTeX: tables, text, links, captions

## Setup

```latex
\usepackage{paper-colors}             % any order relative to tikz / pgfplots / hyperref
% \usepackage[hyperref]{paper-colors} % also color links with cLink (see below)
```

It loads `xcolor` and `colortbl` and defines every theme color — anchors `cOurs`, `cBase1`…, `cNeutral` (each line comments its book code), ramp steps `cOursS1` (lightest) … `cOursS5` (darkest), text colors `cHighlight`, `cGain`, `cDrop`, `cLink` (taken from ramp steps), `cArrow`, diagram colors — and the commands below. The commands are defined at `\begin{document}` with `\providecommand`, so if the paper already defines `\best` (common in ML papers) its own version wins; check that it still means "bold best".

## Tables

| Command | Effect | Use for |
|---|---|---|
| `\best{74.3}` | bold | best number per column |
| `\second{72.0}` | underline | second best |
| `\oursrow` | `cOursS1` row shading | start of our method's row(s) |
| `\hlcell` | `cHighlight` cell background | one cell the text discusses |
| `\gain{+2.3}` / `\drop{-0.4}` | theme's gain / drop text color | deltas vs a reference row |

```latex
\begin{tabular}{lcc}\toprule
Method & Acc & F1 \\ \midrule
Baseline A & 71.2 & \second{60.1} \\
\oursrow Ours & \best{74.3} & \best{62.0} \\
\quad w/o X & 73.1 \drop{(-1.2)} & 61.2 \\ \bottomrule
\end{tabular}
```

- Bold/underline carry "best/second"; color is redundant decoration on top, never the only cue.
- Rows for ordered variants (model sizes, data scales) may be shaded with the matching ramp steps, light → dark, the same steps as in the figures: `\rowcolor{cOursS1}` … `\rowcolor{cOursS3}` (stay at steps 1–3 behind black text).
- Shade only our rows, not every other row (no zebra stripes with `booktabs`).
- Deltas always carry a sign; the sign is the primary cue, color the secondary one.

## Text and captions

- Body text stays black. Colored words for emphasis are not allowed.
- Tie text to a figure with swatches: `Ours (\swatch{cOurs}) vs.\ Baseline A (\swatch{cBase1})`. Use the role of the method, so the swatch matches the plot.
- Method names in text are not colored.

## Links

Many venue templates (CVPR, ICCV, ECCV, ACL) already configure `hyperref` colors — leave them. When the template does not and you want colored links, load with `[hyperref]` and load `hyperref` yourself; then links/cites/URLs use `cLink` (8:1 contrast, prints as near-black). Never use the default bright red/green link boxes.

## Overleaf / git

Commit the exported `paper-colors.sty` into the paper repo (Overleaf compiles it like any local file). To change the theme, re-export and commit; do not edit the `.sty` by hand.
