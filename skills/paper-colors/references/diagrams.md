# Method / architecture diagrams

A diagram uses **at most three fill colors plus gray**. Color says what a box *is*, never decoration.

| Diagram role | Use for | Stroke | Fill |
|---|---|---|---|
| `trainable` | our new / trained modules | `ours` anchor | `ours` step 1 |
| `frozen` | pretrained or fixed modules, generic blocks | `neutral` anchor | `neutral` step 1 |
| `data` | inputs, datasets, tokens, features | `base2` anchor | `base2` step 1 |
| `loss` | objectives, losses, rewards | `base1` anchor | `base1` step 1 |
| `output` | predictions, outputs | `base3` anchor | `base3` step 1 |
| arrows | data flow | `neutral` step 4 (`cArrow`), 0.8pt | — |
| key path | the flow that is our contribution | `ours`, 1.2pt | — |

Exact hex values per theme: `show <theme>` or the exported `paper-colors.json` → `diagram`. Boxes keep **black text** (step-1 fills are L* ≈ 92). Several stages of one pipeline that differ only in degree (e.g. coarse → fine) may use steps 1–3 of the same hue as fills.

Rules:
- `trainable` (ours) must match `ours` in the plots: readers link "blue box" in Fig. 1 with "blue line" in Fig. 4.
- Skip roles you do not need; an encoder–decoder figure may be only `frozen` + `trainable` + arrows.
- Emphasize with stroke weight or one `pc ours arrow`, not by adding colors. A frozen-vs-trainable distinction can add icons (snowflake / flame), never a second blue.
- Icons, images and example inputs keep their natural colors; put them inside a `neutral` frame.
- Same module drawn twice (e.g. shared weights) → same style both times.

## TikZ

`paper-colors.sty` defines the styles once `tikz` is loaded:

```latex
\usetikzlibrary{positioning}
\begin{tikzpicture}[node distance=6mm and 8mm]
  \node[pc data]      (x)   {Input};
  \node[pc frozen,    right=of x]   (enc) {Encoder};
  \node[pc trainable, right=of enc] (ad)  {Adapter};
  \node[pc output,    right=of ad]  (y)   {Output};
  \node[pc loss,      below=of y]   (l)   {Loss};
  \draw[pc arrow] (x) -- (enc);  \draw[pc ours arrow] (enc) -- (ad);
  \draw[pc arrow] (ad) -- (y);   \draw[pc arrow] (y) -- (l);
\end{tikzpicture}
```

Colors as names: `cTrainable` / `cTrainableFill`, `cFrozen` / `cFrozenFill`, `cData…`, `cLoss…`, `cOutput…`, `cArrow`. Region backgrounds (grouping several boxes): `fill=cOursS1!50, draw=none`.

## draw.io / diagrams.net

`paper-colors.json` → `diagram.<role>.drawio_style` is a ready style string, e.g. `fillColor=<step-1 hex>;strokeColor=<anchor hex>;fontColor=#000000;rounded=1;`. Select a shape → *Edit Style* → paste. Save one styled shape per role into a scratchpad library so the whole figure reuses them. Run `lint` over the `.drawio` file afterwards (it is scanned).

## PowerPoint / Keynote / Figma

Enter the hex values from `paper-colors.json` (`diagram.*.fill`, `diagram.*.stroke`, `arrow`) as custom/document colors once (PowerPoint: *Design → Variants → Colors → Customize*; Figma: create color styles named after the roles). Export as PDF (vector) for LaTeX. Also export an SVG copy if you want `lint` to check it: it reads hex, `rgb()` and named colors in `.svg` and `.drawio` files, not in PDF / PPTX / Figma files.
