"""ASE (Pantone Connect collection export) reading and registry import."""

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

import ase  # noqa: E402
import colorlib as cl  # noqa: E402
import registry  # noqa: E402


def rgb(hex_color):
    return cl.parse_hex(hex_color)


def lab_ase(hex_color):
    l, a, b = cl.to_lab_d50(hex_color)
    return (l / 100, a, b)  # ASE stores L* as 0..1


class LabD50(unittest.TestCase):
    def test_reference_values(self):
        # sRGB red in Lab D50 (Bradford), as published by Lindbloom.
        for got, want in zip(cl.to_lab_d50("#FF0000"), (54.29, 80.81, 69.89)):
            self.assertAlmostEqual(got, want, places=1)
        self.assertAlmostEqual(cl.to_lab_d50("#FFFFFF")[0], 100.0, places=3)

    def test_round_trip(self):
        for h in ("#174A7C", "#B22C4C", "#949699", "#F0DC55", "#000000"):
            back, ok = cl.lab_d50_to_hex(cl.to_lab_d50(h))
            self.assertEqual(back, h)
            self.assertTrue(ok)

    def test_out_of_gamut_flagged(self):
        self.assertFalse(cl.lab_d50_to_hex((50, 120, 0))[1])


class ReadAse(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_models_groups_and_codes(self):
        path = self.root / "c.ase"
        ase.write_ase(path, [
            ("PANTONE 00-0001 TCX Test Blue", "RGB", rgb("#174A7C")),
            ("PANTONE 00-0002 TCX", "LAB", lab_ase("#B22C4C")),
            ("PANTONE Test Gray 9 C", "Gray", (0.5,)),
            ("PANTONE 0001 C", "CMYK", (1.0, 0.45, 0.0, 0.14)),
        ], group="My paper")
        got = ase.read_ase(path)
        self.assertEqual([s.code for s in got], ["00-0001 TCX", "00-0002 TCX", "Test Gray 9 C", "0001 C"])
        self.assertEqual(got[0].hex, "#174A7C")
        self.assertLess(cl.delta_e(got[1].hex, "#B22C4C"), 0.5)      # float32 rounding only
        self.assertEqual(got[2].hex, "#808080")
        self.assertIsNone(got[3].hex)
        self.assertIn("CMYK", got[3].note)
        self.assertEqual({s.group for s in got}, {"My paper"})

    def test_not_ase_and_truncated(self):
        bad = self.root / "bad.ase"
        bad.write_bytes(b"PNG....")
        with self.assertRaises(ase.AseError):
            ase.read_ase(bad)
        good = self.root / "good.ase"
        ase.write_ase(good, [("PANTONE 0001 C", "RGB", rgb("#0A4A90"))])
        bad.write_bytes(good.read_bytes()[:-6])
        with self.assertRaises(ase.AseError):
            ase.read_ase(bad)


class ImportAse(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.reg = self.root / "pantone/swatches.json"
        self.file = self.root / "collection.ase"
        ase.write_ase(self.file, [
            ("PANTONE 00-0001 TCX", "RGB", rgb("#174A7C")),
            ("PANTONE 00-0002 TCX", "LAB", lab_ase("#B22C4C")),
            ("PANTONE 0001 C", "CMYK", (1.0, 0.45, 0.0, 0.14)),
            ("Custom swatch", "RGB", rgb("#123456")),
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def statuses(self, report):
        return {r["code"]: r["status"] for r in report}

    def test_dry_run_writes_nothing(self):
        report = registry.import_ase(self.file, path=self.reg, dry_run=True)
        self.assertEqual(self.statuses(report)["00-0001 TCX"], "added")
        self.assertFalse(self.reg.exists())

    def test_import_then_reimport(self):
        report = registry.import_ase(self.file, path=self.reg)
        self.assertEqual(self.statuses(report), {"00-0001 TCX": "added", "00-0002 TCX": "added",
                                                 "0001 C": "skipped", "Custom swatch": "added"})
        reg = registry.load_swatches(self.reg)
        self.assertEqual(reg["00-0001 TCX"]["hex"], "#174A7C")
        self.assertEqual(reg["00-0002 TCX"]["method"], "ase-lab")
        self.assertEqual(reg["00-0001 TCX"]["source"], "imports/collection.ase")
        self.assertTrue((self.root / "pantone/imports/collection.ase").exists())
        again = registry.import_ase(self.file, path=self.reg)
        self.assertEqual(self.statuses(again)["00-0001 TCX"], "unchanged")

    def test_conflict_is_not_overwritten(self):
        registry.add_swatch("00-0001 TCX", "Test Blue", "#B22C4C", None, None, path=self.reg)
        report = registry.import_ase(self.file, path=self.reg)
        self.assertEqual(self.statuses(report)["00-0001 TCX"], "conflict")
        self.assertEqual(registry.load_swatches(self.reg)["00-0001 TCX"]["hex"], "#B22C4C")

    def test_cli_exit_codes(self):
        import paper_colors
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"PAPER_COLORS_SWATCHES": str(self.reg)}), redirect_stdout(buf):
            code = paper_colors.main(["swatch", "import", str(self.file)])
            self.assertEqual(code, 0, buf.getvalue())
            self.assertIn("added 3", buf.getvalue())
            self.assertIn("00-0002 TCX", json.loads(self.reg.read_text()))
            registry.add_swatch("0001 C", "", "#FF0000", None, None, path=self.reg)
            ase.write_ase(self.file, [("PANTONE 0001 C", "RGB", rgb("#0A4A90"))])
            self.assertEqual(paper_colors.main(["swatch", "import", str(self.file)]), 1)  # conflict


if __name__ == "__main__":
    unittest.main()
