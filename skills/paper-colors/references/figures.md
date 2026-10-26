# Data figures

The exported `paper_colors.py` is standalone; put it next to the figure scripts (or on `sys.path`).

```python
from paper_colors import C, RAMP, CVD_SAFE, GRAY_SAFE, apply, style, ramp, tint, cmap
apply()                  # color cycle = anchors; registers paper_sequential / paper_diverging / paper_<role>
# apply(redundant=True)  # cycle color + marker together (grayscale-first venues)
```

`apply()` only touches the color cycle and `image.cmap`; fonts, spines and export settings stay with whatever figure style the project uses. If the user has a figure-style skill installed (for example `scientific-figure-making` from [figures4papers](https://github.com/ChenLiu-1996/figures4papers) by Chen Liu, CC BY-NC 4.0, installed separately), let it own those and keep only the colors here.

## Methods: one hue each

```python
ROLE = {"Ours": 0, "Baseline A": 1, "Baseline B": 2}     # the step-3 role map, as numbers
ax.plot(x, y_ours, color=C["ours"], lw=2.2, zorder=5, label="Ours")
for name, y in baselines.items():
    ax.plot(x, y, lw=1.4, label=name, **style(ROLE[name], redundant=grayscale_print))
```

- `style(i)` takes the **role number** (0 = ours, i = base*i*), not the loop position, so Baseline A keeps its hue in every panel. It never returns `neutral`.
- It adds `marker` + `linestyle` when `i >= CVD_SAFE`, past the last baseline (hues repeat there), or for every series with `redundant=True` — pass that when the figure must survive black-and-white print with more than `GRAY_SAFE` series. With > ~15 points, add `markevery=max(1, len(x) // 8)`.
- Line widths: ours ≈ 2.2pt, baselines ≈ 1.4pt, references (`C["neutral"]`) 1pt dashed.
- No named or format-string colors (`'red'`, `'tab:blue'`, `'r--'`); `lint` flags them. `'C0'`.. are fine after `apply()`.

## Ordered levels: one hue's ramp

Model size, data scale, strength, training steps, ablation completeness — anything ordered — use **one hue, light → dark**:

```python
sizes = ["S", "M", "L"]
for c, s in zip(ramp("ours", len(sizes), lightest=2), sizes):   # steps 2, 3/4, 5
    ax.plot(x, y[s], color=c, lw=1.8, label=f"Ours-{s}")
```

- `ramp(role, n, lightest=1)` returns `n` evenly spread steps from `lightest` to the darkest, both ends included; `ramp(role)` all 5; `ramp(role, 1)` the anchor. **Lines and markers: `lightest=2`** — step 1 (L* ≈ 92) is a fill color and nearly vanishes as a line. Bars, areas and table shading may use step 1. More than 4–5 levels: set `"steps": 7` in the theme rather than inventing in-between colors.
- The hue says *which method*, the step says *which level*: "Ours-S/M/L" use the ours ramp, "Baseline-S/M/L" the base1 ramp, with the same step per size in both.
- **Ablations** (one method, increasingly complete): the ours ramp, full model darkest.

## Bars

```python
ax.bar(names, vals, color=[C["ours"], C["base1"], C["base2"]], edgecolor="black", linewidth=0.8)
ax.bar(sizes, acc, color=ramp("ours", len(sizes)), edgecolor=C["ours"], linewidth=0.8)  # ordered
```

- Anchors with < 3:1 contrast (`audit` warns) are fine as fills with a dark edge, not as thin lines.
- Grouped bars: color = method (hue), hatch = sub-condition (`"//"`, `"\\\\"`, `".."`) — hatches survive grayscale.

## Transparency

`alpha` is allowed wherever things overlap: std bands (`fill_between(..., color=C["ours"], alpha=0.15, lw=0)`), dense scatter (`alpha=0.5`), stacked histograms. Over white, `alpha=a` looks like `tint(color, a)`, so it stays on-palette. Do not use alpha to encode an ordered level — use ramp steps, which are spaced for visibility and print.

## Heatmaps and colormaps

Never a rainbow colormap (`jet`, `hsv`, `turbo`, `rainbow`, …): lightness is not monotonic, so it invents boundaries and fails in grayscale.

| Data | Colormap |
|---|---|
| magnitude, one-signed (accuracy, attention) | `paper_sequential` (= the ours ramp) or `paper_<role>` |
| signed, meaningful 0 (delta, correlation) | `paper_diverging` with `TwoSlopeNorm(vcenter=0)` or symmetric `vmin=-v, vmax=v` |
| categorical cells | `ListedColormap([C[r] for r in roles])`, ≤ CVD_SAFE entries |

```python
from matplotlib.colors import TwoSlopeNorm
im = ax.imshow(delta, cmap="paper_diverging", norm=TwoSlopeNorm(vcenter=0))
```

Annotated cells: black text on cells with L* > 55, white otherwise.

## Scatter / embeddings (t-SNE, UMAP)

Points by class: anchors (`C["ours"]`, `C["base1"]`, …) with `s=6, alpha=0.6, linewidths=0`; for more classes than CVD_SAFE also vary `marker`. Highlighted subset in `C["ours"]`, larger, on top; the rest may go `C["neutral"]` at low alpha.

## pgfplots

With `\usepackage{paper-colors}` in the preamble:

```latex
\begin{axis}[cycle list name=paper]            % anchors with distinct marks
\addplot[cOurs, very thick, mark=*] ...;
\addplot[cOursS2] ...; \addplot[cOursS4] ...;    % ordered levels
\begin{axis}[colormap name=paperseq]             % / paperdiv / paperours / paperbase1 ...
```
