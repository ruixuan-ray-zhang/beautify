"""Pantone Connect verification: checklist, parsing, comparison, registry records."""

import io
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

import library  # noqa: E402
import registry  # noqa: E402
import paper_colors  # noqa: E402
import verify  # noqa: E402
from test_colorbooks import BOOK, write_acb  # noqa: E402


class Parsing(unittest.TestCase):
    def test_free_lines(self):
        connect, rows = verify.parse_values("PANTONE 0001 C  #0A4A90\n0002 C, D2331F\nnoise line\n")
        self.assertEqual(connect, {"0001 C": "#0A4A90", "0002 C": "#D2331F"})
        self.assertEqual(rows, {})

    def test_filled_checklist(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = verify.write_checklist([{"code": "0001 C", "source": "b", "our_hex": "#0A4A90",
                                            "outside_srgb": ""}], Path(tmp) / "c.tsv")
            text = path.read_text().replace("\t\n", "\t#004C98\n")
        connect, rows = verify.parse_values(text)
        self.assertEqual(connect, {"0001 C": "#004C98"})
        self.assertEqual(rows["0001 C"]["our_hex"], "#0A4A90")

    def test_status_bands(self):
        self.assertEqual([verify.status(d) for d in (0.5, 3, 9)], ["ok", "check", "mismatch"])


class Flow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.reg = self.root / "pantone/swatches.json"
        self.env = mock.patch.dict(os.environ, {"PAPER_COLORS_SWATCHES": str(self.reg)})
        self.env.start()
        book = self.root / "solid.acb"
        write_acb(book, {k[:-2]: v for k, v in BOOK.items()})
        library.add_library(book, self.root / "pantone/libraries", "Solid")

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = paper_colors.main(list(argv))
        return code, out.getvalue()

    def test_sample_checklist(self):
        code, out = self.cli("swatch", "verify", "--library", "Solid", "--sample", "3")
        self.assertEqual(code, 0, out)
        files = list((self.root / "pantone/verify").glob("*-sample-solid.tsv"))
        self.assertEqual(len(files), 1)
        self.assertEqual(len(files[0].read_text().splitlines()), 4)   # header + 3

    def test_registered_verify_and_adopt(self):
        self.cli("swatch", "add", "0001 C", "--from-library")
        self.cli("swatch", "add", "0002 C", "--from-library")
        code, out = self.cli("swatch", "verify")
        self.assertEqual(code, 0)
        self.assertIn("0001 C", out)
        ours = registry.load_swatches(self.reg)["0001 C"]["hex"]
        values = self.root / "connect.txt"
        values.write_text(f"0001 C {ours}\n0002 C #FF0000\n")
        code, out = self.cli("swatch", "verify", "--values", str(values))
        self.assertEqual(code, 1, out)                                # 0002 C differs
        reg = registry.load_swatches(self.reg)
        self.assertEqual(reg["0001 C"]["verified"]["status"], "ok")
        self.assertIn(reg["0002 C"]["verified"]["status"], ("check", "mismatch"))
        self.assertNotEqual(reg["0002 C"]["hex"], "#FF0000")           # not adopted
        code, _ = self.cli("swatch", "verify", "--values", str(values), "--adopt")
        reg = registry.load_swatches(self.reg)
        self.assertEqual(reg["0002 C"]["hex"], "#FF0000")
        self.assertIn("book_hex", reg["0002 C"])
        code, out = self.cli("swatch", "verify")                     # only unverified/failed left
        self.assertNotIn("0001 C", out)

    def test_book_code_without_registry(self):
        values = self.root / "v.txt"
        values.write_text("0003 C #F2E66A\n9999 C #000000\n")
        code, out = self.cli("swatch", "verify", "--values", str(values))
        self.assertIn("unknown", out)
        self.assertIn("0003 C", out)


if __name__ == "__main__":
    unittest.main()
