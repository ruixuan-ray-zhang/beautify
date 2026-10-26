"""Harmonies (Connect's when indexed, else computed in OKLCh), JSON output, swatches,
and the Delta E00 reading. Synthetic data only."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

import colorlib as cl  # noqa: E402
import harmony  # noqa: E402
import library  # noqa: E402
import paper_colors  # noqa: E402
import term  # noqa: E402
from test_pantone_cli import synthetic_index  # noqa: E402


class ComputedTargetsTest(unittest.TestCase):
    def test_complement_is_opposite_hue_same_lightness(self):
        base = "#1F4E99"
        (comp,) = harmony.targets(base, "COMPLEMENTARY")
        l0, _, h0 = cl.to_oklch(base)
        l1, _, h1 = cl.to_oklch(comp)
        self.assertAlmostEqual(cl.hue_distance(h0, h1), 180, delta=3)
        self.assertAlmostEqual(l0, l1, delta=0.01)

    def test_counts_and_mono_keeps_hue(self):
        self.assertEqual(len(harmony.targets("#E0703A", "TETRADIC")), 3)
        hues = [cl.to_oklch(h)[2] for h in harmony.targets("#E0703A", "MONOCHROMATIC")]
        base_hue = cl.to_oklch("#E0703A")[2]
        self.assertTrue(all(cl.hue_distance(h, base_hue) < 6 for h in hues))

    def test_unknown_kind(self):
        with self.assertRaises(KeyError):
            harmony.targets("#123456", "PENTADIC")


class HarmonyCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        index = root / "index.json"
        index.write_text(json.dumps(synthetic_index()))
        self.env = mock.patch.dict(os.environ, {"PAPER_COLORS_SWATCHES": str(root / "swatches.json")})
        self.env.start()
        library.add_pantone_cli(index, root / "libraries")

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_json(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(paper_colors.main(argv), 0)
        return json.loads(buf.getvalue())

    def test_connect_harmony_wins_for_indexed_code(self):
        out = self.run_json(["swatch", "harmony", "TEST 1 C", "--kind", "complementary", "--json"])
        (row,) = out["harmonies"]["COMPLEMENTARY"]
        self.assertEqual((row["source"], row["code"]), ("connect", "TEST 2 C"))
        self.assertIn("not affiliated", out["disclaimer"].lower())

    def test_kind_spellings_and_no_color_anywhere(self):
        for kind in ("TRIADIC", "split_complementary", "split-complementary"):
            out = self.run_json(["swatch", "harmony", "TEST 1 C", "--kind", kind, "--json", "--no-color"])
            self.assertEqual(len(out["harmonies"]), 1)

    def test_computed_harmony_snaps_to_book(self):
        out = self.run_json(["swatch", "harmony", "TEST 1 C", "--kind", "triadic",
                             "--library", "Test Solid Coated", "--json"])
        rows = out["harmonies"]["TRIADIC"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["source"] == "computed" and r["code"].endswith(" C") for r in rows))

    def test_hex_anchor_without_books_gives_targets(self):
        with mock.patch.dict(os.environ, {"PAPER_COLORS_SWATCHES": str(Path(self.tmp.name) / "x" / "s.json")}):
            out = self.run_json(["swatch", "harmony", "#1F4E99", "--kind", "analogous", "--json"])
        self.assertTrue(all(r["code"] is None and r["target"].startswith("#")
                            for r in out["harmonies"]["ANALOGOUS"]))

    def test_match_json(self):
        out = self.run_json(["swatch", "match", "#2050A0", "--library", "Test Solid Coated", "--json"])
        self.assertEqual(out["method"], "CIEDE2000")
        (res,) = out["results"]
        self.assertEqual(res["chosen"]["code"], "TEST 1 C")
        self.assertIn(res["chosen"]["perceived"], [name for _, name in library.PERCEPTION])
        self.assertEqual(out["registered"], [])

    def test_match_text_has_disclaimer_and_no_ansi_when_piped(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            paper_colors.main(["swatch", "match", "#2050A0"])
        self.assertIn("CIEDE2000", buf.getvalue())
        self.assertNotIn("\x1b[", buf.getvalue())


class PerceptionAndSwatchTest(unittest.TestCase):
    def test_scale(self):
        self.assertEqual(library.perceive(0.5), "not perceptible")
        self.assertEqual(library.perceive(3.0), "noticeable")
        self.assertEqual(library.perceive(12.0), library.NO_GOOD_MATCH)

    def test_swatch_respects_tty_and_no_color(self):
        tty = mock.patch("sys.stdout.isatty", return_value=True)
        with tty, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NO_COLOR", None)
            self.assertIn("\x1b[48;2;255;0;0m", term.swatch("#FF0000"))
            with mock.patch.dict(os.environ, {"NO_COLOR": "1"}):
                self.assertEqual(term.swatch("#FF0000"), "")
            with mock.patch.dict(os.environ, {"NO_COLOR": ""}):    # empty: colors stay on
                self.assertNotEqual(term.swatch("#FF0000"), "")


if __name__ == "__main__":
    unittest.main()
