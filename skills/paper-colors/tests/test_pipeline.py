"""Themes, ramps, exporters and lint, end to end on temp dirs, against tests/fixtures
(invented codes; the real pantone/swatches.json is never touched)."""

import dataclasses
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ["PAPER_COLORS_PALETTES"] = str(HERE / "fixtures/palettes.json")
os.environ["PAPER_COLORS_SWATCHES"] = str(HERE / "fixtures/swatches.json")
sys.path.insert(0, str(HERE.parent / "scripts"))

import colorlib as cl  # noqa: E402
import lint  # noqa: E402
import paper_colors  # noqa: E402
import ramps  # noqa: E402
import themes  # noqa: E402


def run_cli(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = paper_colors.main(list(argv))
    return code, buf.getvalue()


class Ramps(unittest.TestCase):
    def test_derived_ramp_keeps_anchor_and_hue(self):
        for anchor in ("#174A7C", "#B22C4C", "#F0DC55", "#949699", "#FFBE98"):
            ramp, k = ramps.derive(anchor, 5)
            self.assertEqual(ramp[k], anchor)
            ls = [cl.lightness(c) for c in ramp]
            self.assertEqual(ls, sorted(ls, reverse=True), anchor)
            self.assertTrue(all(a - b >= themes.MIN_RAMP_STEP for a, b in zip(ls, ls[1:])), (anchor, ls))
            _, chroma, hue = cl.to_oklch(anchor)
            if chroma > 0.05:
                for c in ramp:
                    self.assertLess(cl.hue_distance(cl.to_oklch(c)[2], hue), 6, (anchor, c))

    def test_step_counts(self):
        for n in (3, 5, 7):
            self.assertEqual(len(ramps.derive("#174A7C", n)[0]), n)


class ThemeAudit(unittest.TestCase):
    def setUp(self):
        self.theme = themes.load("fixture")

    def test_fixture_passes(self):
        errors = [m for lvl, m in themes.audit(self.theme) if lvl == "ERROR"]
        self.assertEqual(errors, [])

    def test_ramp_kinds(self):
        t = self.theme
        self.assertTrue(all(t.ramp_codes["base1"]))                 # explicit book ramp
        self.assertEqual(t.ramp_codes["base1"][t.anchor_step["base1"] - 1], "TEST B1")
        self.assertEqual(sum(c is not None for c in t.ramp_codes["ours"]), 1)  # derived
        self.assertEqual(t.ramps["ours"][t.anchor_step["ours"] - 1], t.anchors["ours"])

    def test_text_roles_come_from_ramps(self):
        t = self.theme
        self.assertEqual(t.text["highlight"], t.ramps["ours"][0])
        self.assertEqual(t.text["gain"], t.ramps["base2"][-1])

    def test_audit_catches_red_green_pair(self):
        anchors = {**self.theme.anchors, "base1": "#D62728", "base2": "#2CA02C"}
        bad = dataclasses.replace(self.theme, anchors=anchors)
        errors = [m for lvl, m in themes.audit(bad) if lvl == "ERROR"]
        self.assertTrue(any("deutan" in m or "protan" in m for m in errors), errors)

    def test_audit_catches_flat_pantone_ramp(self):
        r = list(self.theme.ramps["base1"])
        r[1], r[2] = r[2], r[1]                                        # not light -> dark
        bad = dataclasses.replace(self.theme, ramps={**self.theme.ramps, "base1": r})
        errors = [m for lvl, m in themes.audit(bad) if lvl == "ERROR"]
        self.assertTrue(any("base1 book ramp" in m for m in errors), errors)

    def test_unknown_pantone_code_is_reported(self):
        with self.assertRaises(themes.ThemeError):
            themes._hex_for("00-0001 TCX", {}, "x")


class ExportAndLint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.theme = themes.load("fixture")

    def tearDown(self):
        self.tmp.cleanup()

    def test_export_writes_all_formats_and_module_works(self):
        code, _ = run_cli("export", "fixture", "--out", str(self.root))
        self.assertEqual(code, 0)
        for name in ("paper_colors.py", "paper-colors.sty", "paper-colors.json",
                     "paper-colors-swatches.svg"):
            self.assertTrue((self.root / name).is_file(), name)
        ns = {}
        exec((self.root / "paper_colors.py").read_text(), ns)
        C, style, ramp = ns["C"], ns["style"], ns["ramp"]
        self.assertEqual(ns["CODES"]["ours"], "TEST OURS")
        self.assertEqual(style(0), {"color": C["ours"]})
        self.assertEqual(style(1)["color"], C["base1"])
        self.assertIn("marker", style(1, redundant=True))
        n_series = len(ns["SERIES"])
        self.assertEqual(style(n_series)["color"], C["base1"])         # wraps past last baseline
        self.assertIn("marker", style(n_series, redundant=False))
        self.assertNotIn(C["neutral"], {style(i)["color"] for i in range(20)})
        self.assertEqual(ramp("ours"), ns["RAMP"]["ours"])
        self.assertEqual(ramp("ours", 3), [ns["RAMP"]["ours"][i] for i in (0, 2, 4)])
        self.assertEqual(ramp("base1", 1), [C["base1"]])
        self.assertEqual(ramp("ours", 3, lightest=2), [ns["RAMP"]["ours"][i] for i in (1, 3, 4)])
        self.assertEqual(ramp("ours", lightest=2), ns["RAMP"]["ours"][1:])
        with self.assertRaises(ValueError):
            ramp("ours", 5, lightest=2)
        with self.assertRaises(ValueError):
            ramp("ours", 6)
        for bad in (("332288", 1.5), ("#12345", 0.5)):
            with self.assertRaises(ValueError):
                ns["tint"](*bad)
        sty = (self.root / "paper-colors.sty").read_text()
        self.assertIn("\\definecolor{cOurs}{HTML}{332288} % code TEST OURS", sty)
        self.assertIn("\\definecolor{cBase1S1}", sty)
        self.assertIn("\\providecommand{\\best}", sty)
        self.assertNotIn("\\newcommand", sty)

    def test_no_themes_is_not_an_error(self):
        empty = self.root / "palettes.json"
        empty.write_text('{"defaults": {"diagram": {}}, "default_theme": null, "themes": {}}')
        self.assertEqual(themes.load_all(empty)[0], {})

    def test_lint_detects_theme_and_flags_only_violations(self):
        run_cli("export", "fixture", "--out", str(self.root), "--formats", "sty")
        step = self.theme.ramps["base2"][1]
        (self.root / "fig.py").write_text(
            'ax.plot(x, y, color="red")\n'
            f'ax.bar(n, v, color="{step}")\n'              # ramp step -> allowed
            f'ax.bar(n, v, color="{cl.tint(self.theme.anchors["ours"], 0.3)}")\n'  # tint -> allowed
            'ax.axhline(0, color="#999999")\n'             # gray -> allowed
            'plt.imshow(z, cmap="jet_r")\n')
        (self.root / "main.tex").write_text(
            "\\textcolor{cOurs}{ok} \\cellcolor{cBase2S2} \\textcolor{blue}{bad} % \\color{red}\n"
            "\\definecolor{x}{HTML}{00FF00}\n")
        self.assertEqual(lint.detect_theme(self.root), "fixture")
        findings = lint.lint_tree(self.root, self.theme)
        got = sorted((f.path.name, f.line, f.kind) for f in findings)
        self.assertEqual(got, [("fig.py", 1, "mpl-name"), ("fig.py", 5, "rainbow-cmap"),
                               ("main.tex", 1, "tex-name"), ("main.tex", 2, "hex")])
        code, _ = run_cli("lint", str(self.root))
        self.assertEqual(code, 1)

    def test_lint_regressions_from_review(self):
        ours = self.theme.anchors["ours"]
        (self.root / "macros.tex").write_text("\\definecolor{brand}{HTML}{" + ours[1:] + "}\n")
        (self.root / "sec.tex").write_text(
            "\\textcolor{brand}{ok}\n"                                    # 1 defined elsewhere
            "\\textcolor[HTML]{" + ours[1:] + "}{ok}\n"                  # 2 = ours via model
            "\\href{https://x.org/#ff0000}{ok} 5\\% \\textcolor{red}{bad}\n"
            "\\draw[red, thick] (0,0); \\node[fill=cOurs!10, text=white] {};\n"
            "\\colorlet{mine}{orange}\n"
            "\\begin{axis}[colormap/jet]\n"
            "\\textcolor[RGB]{255,0,255}{bad}\n")
        (self.root / "f.py").write_text(
            "ax.bar(n, v, color=['red', C['ours']])\n"
            "ax.plot(x, y, 'r--')\n"
            "plt.get_cmap('hsv'); ax.plot(x, y, color='0.5')\n"
            f'ax.plot(x, y, color="{ours}CC")\n'
            'style = {"color": "magenta"}\n')
        (self.root / "d.svg").write_text('<path fill="rgb(255,0,255)" stroke="magenta" '
                                         'style="fill:url(#g)"/>\n')
        (self.root / "n.ipynb").write_text('{"source": ["ax.plot(x, y, color=\\"red\\")\\n"]}\n')
        findings = lint.lint_tree(self.root, self.theme)
        got = sorted((f.path.name, f.line, f.kind, f.value) for f in findings)
        self.assertEqual(got, [
            ("d.svg", 1, "named", "magenta"), ("d.svg", 1, "rgb", "rgb(255,0,255)"),
            ("f.py", 1, "mpl-name", "red"), ("f.py", 2, "mpl-name", "r"),
            ("f.py", 3, "rainbow-cmap", "hsv"), ("f.py", 5, "mpl-name", "magenta"),
            ("n.ipynb", 1, "mpl-name", "red"),
            ("sec.tex", 3, "tex-name", "red"), ("sec.tex", 4, "tex-name", "red"),
            ("sec.tex", 5, "tex-name", "orange"), ("sec.tex", 6, "rainbow-cmap", "jet"),
            ("sec.tex", 7, "rgb", "[RGB]{255,0,255}"),
        ])

    def test_lint_clean_project_exits_zero(self):
        (self.root / "fig.py").write_text('ax.plot(x, y, color=C["ours"])\n')
        code, out = run_cli("lint", str(self.root), "--theme", "fixture")
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
