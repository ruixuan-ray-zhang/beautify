"""Palette-entry resolution: code first, else a close color, lighter by default."""

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import colorlib as cl  # noqa: E402
import library  # noqa: E402
import registry  # noqa: E402
import paper_colors  # noqa: E402
from colorbooks import BookColor  # noqa: E402


def book(entries):
    return [BookColor(code, f"PANTONE {code}", "Lab", cl.to_lab(h), h) for code, h in entries]


TARGET = "#7A7A7A"                       # mid gray, L* ~51
LIBS = {
    "TCX": book([("00-0011 TCX", "#F2F5EE"), ("00-0017 TCX", "#777777"),   # just darker, nearest
                 ("00-0016 TCX", "#818181"),                                 # lighter, slightly farther
                 ("00-0018 TCX", "#5A5A5A")]),
    "TPG": book([("00-0011 TPG", "#F1F0ED"), ("00-0004 TPG", "#C7E4CA")]),
}


class Variants(unittest.TestCase):
    def test_suffix_completion(self):
        self.assertEqual(library.code_variants("00-0004")[:2], ["00-0004 TCX", "00-0004 TPG"])
        self.assertEqual(library.code_variants("PANTONE 0001"), ["0001 C", "0001 U"])
        self.assertEqual(library.code_variants("00-0001 TCX"), ["00-0001 TCX"])

    def test_exact_prefers_tcx_then_tpg(self):
        self.assertEqual(library.lookup_any("00-0011", LIBS)[0][0], "TCX")
        self.assertEqual(library.lookup_any("00-0004", LIBS)[0][0], "TPG")    # only TPG has it
        self.assertEqual(library.lookup_any("00-0011", LIBS, "TPG")[0][0], "TPG")


class Resolve(unittest.TestCase):
    def test_code_found_wins_over_color(self):
        res = library.resolve("00-0011", "#000000", LIBS)
        self.assertEqual((res["status"], res["chosen"][1].code), ("exact", "00-0011 TCX"))

    def test_missing_code_prefers_lighter_within_slack(self):
        res = library.resolve("00-9999", TARGET, LIBS)
        self.assertEqual(res["status"], "approx")
        self.assertEqual(res["candidates"][0][1].code, "00-0017 TCX")         # nearest is darker
        self.assertEqual(res["chosen"][1].code, "00-0016 TCX")               # but lighter is picked
        self.assertIn("lighter", res["reason"])

    def test_other_preferences(self):
        self.assertEqual(library.resolve(None, TARGET, LIBS, prefer="nearest")["chosen"][1].code, "00-0017 TCX")
        self.assertEqual(library.resolve(None, TARGET, LIBS, prefer="darker")["chosen"][1].code, "00-0017 TCX")

    def test_lighter_too_far_falls_back_to_nearest(self):
        libs = {"TCX": book([("00-0017 TCX", "#777777"), ("00-0013 TCX", "#C8C8C8")])}
        res = library.resolve(None, TARGET, libs)
        self.assertEqual(res["chosen"][1].code, "00-0017 TCX")
        self.assertIn("no lighter", res["reason"])

    def test_far_and_none(self):
        libs = {"TCX": book([("00-0011 TCX", "#F2F5EE")])}
        self.assertEqual(library.resolve(None, "#202020", libs)["status"], "far")
        self.assertEqual(library.resolve("99-9999", None, libs)["status"], "none")


class Cli(unittest.TestCase):
    def test_register_chosen_skip_far(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lib_dir = root / "pantone/libraries"
            lib_dir.mkdir(parents=True)
            import json
            for name, colors in LIBS.items():
                (lib_dir / f"{name.lower()}.json").write_text(json.dumps({"name": name, "colors": [
                    {"code": c.code, "name": c.name, "model": "Lab", "lab": list(c.lab), "hex": c.hex,
                     "in_gamut": True} for c in colors]}))
            out = io.StringIO()
            with mock.patch.dict(os.environ, {"PAPER_COLORS_SWATCHES": str(root / "pantone/swatches.json")}), \
                    redirect_stdout(out):
                code = paper_colors.main(["swatch", "match", "00-0011", f"00-9999={TARGET}",
                                          "99-0000=#FF00FF", "--register"])
            self.assertEqual(code, 0, out.getvalue())
            reg = registry.load_swatches(root / "pantone/swatches.json")
            self.assertEqual(set(reg), {"00-0011 TCX", "00-0016 TCX"})
            self.assertIn("skip", out.getvalue())


if __name__ == "__main__":
    unittest.main()
