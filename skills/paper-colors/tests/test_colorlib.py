"""Run: python3 -m unittest discover -s ~/.claude/skills/paper-colors/tests"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import colorlib as cl  # noqa: E402


class DeltaE2000(unittest.TestCase):
    # Sharma, Wu & Dalal (2005) reference pairs.
    CASES = [
        ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
        ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
        ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
        ((50.0, 2.5, 0.0), (50.0, 3.1736, 0.5854), 1.0000),
        ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
        ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ]

    def test_reference_pairs(self):
        for lab1, lab2, expected in self.CASES:
            self.assertAlmostEqual(cl.delta_e_lab(lab1, lab2), expected, places=3)
            self.assertAlmostEqual(cl.delta_e_lab(lab2, lab1), expected, places=3)


class Basics(unittest.TestCase):
    def test_hex_roundtrip(self):
        self.assertEqual(cl.to_hex(cl.parse_hex("#0f4d92")), "#0F4D92")

    def test_bad_hex(self):
        with self.assertRaises(ValueError):
            cl.parse_hex("#12345")

    def test_contrast_extremes(self):
        self.assertAlmostEqual(cl.contrast_ratio("#000000"), 21.0, places=2)
        self.assertAlmostEqual(cl.contrast_ratio("#FFFFFF"), 1.0, places=2)
        self.assertAlmostEqual(cl.contrast_ratio("#767676"), 4.54, places=2)

    def test_lab_white_black(self):
        self.assertAlmostEqual(cl.lightness("#FFFFFF"), 100.0, places=2)
        self.assertAlmostEqual(cl.lightness("#000000"), 0.0, places=2)

    def test_tint_matches_xcolor(self):
        # xcolor: red!20 == 20% red + 80% white in sRGB.
        self.assertEqual(cl.tint("#FF0000", 0.2), "#FFCCCC")
        self.assertEqual(cl.shade("#FF0000", 0.5), "#800000")

    def test_cvd_gray_is_fixed_point(self):
        for kind in cl.CVD_MATRICES:
            self.assertLess(cl.delta_e(cl.simulate_cvd("#808080", kind), "#808080"), 1.0)

    def test_cvd_red_green_collapse(self):
        red, green = "#D62728", "#2CA02C"
        self.assertGreater(cl.delta_e(red, green), 40)
        d = cl.delta_e(cl.simulate_cvd(red, "deutan"), cl.simulate_cvd(green, "deutan"))
        self.assertLess(d, 15)

    def test_nearest_tint(self):
        t, d = cl.nearest_tint(cl.tint("#0F4D92", 0.3), "#0F4D92")
        self.assertAlmostEqual(t, 0.3, places=2)
        self.assertLess(d, 0.5)


if __name__ == "__main__":
    unittest.main()
