"""Color book readers (.acb / .aco / .ase), the local library index, and matching.
Books are generated here from the published layouts with invented codes; a real
Pantone book from the user is the remaining check."""

import io
import os
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import ase  # noqa: E402
import colorbooks  # noqa: E402
import colorlib as cl  # noqa: E402
import library  # noqa: E402
import registry  # noqa: E402
import paper_colors  # noqa: E402

try:
    from PIL import Image
except ImportError:
    Image = None

BOOK = {"0003 C": "#F2E66A", "0001 C": "#0A4A90", "0002 C": "#D2331F", "0004 C": "#A52A30",
        "Test Gray 9 C": "#777A7D", "0006 C": "#10A848"}


def _ustr(text: str) -> bytes:
    data = text.encode("utf-16-be")
    return struct.pack(">I", len(data) // 2) + data


def write_acb(path: Path, colors: dict, ctype: int = 7, title="$$$/colorbook/t=TEST Solid Coated",
              prefix="PANTONE ", postfix=" C", empty_slot=True) -> None:
    """colors: {name without prefix/postfix: hex}."""
    out = b"8BCB" + struct.pack(">HH", 1, 3000)
    out += b"".join(_ustr(s) for s in (title, prefix, postfix, "test book"))
    records = []
    for name, hex_c in colors.items():
        if ctype == 7:
            l, a, b = cl.to_lab_d50(hex_c)
            comps = bytes([round(l * 255 / 100), round(a) + 128, round(b) + 128])
        elif ctype == 0:
            comps = bytes(round(c * 255) for c in cl.parse_hex(hex_c))
        else:
            comps = bytes(4)
        records.append(_ustr(name) + name.replace(" ", "")[:6].ljust(6).encode() + comps)
    if empty_slot:
        records.append(_ustr("") + b" " * 6 + bytes(4 if ctype == 2 else 3))
    out += struct.pack(">HHHH", len(records), 7, 1, ctype) + b"".join(records)
    path.write_bytes(out + b"spflspot")


def write_aco(path: Path, colors: list, named: bool = True) -> None:
    """colors: [(name, space, (w, x, y, z))]."""
    v1 = struct.pack(">HH", 1, len(colors)) + b"".join(struct.pack(">5H", s, *v) for _, s, v in colors)
    v2 = struct.pack(">HH", 2, len(colors)) + b"".join(
        struct.pack(">5H", s, *v) + _ustr(n + "\x00") for n, s, v in colors)
    path.write_bytes(v1 + (v2 if named else b""))


def aco_lab(hex_c):
    l, a, b = cl.to_lab_d50(hex_c)
    sa, sb = struct.unpack(">HH", struct.pack(">hh", round(a * 100), round(b * 100)))
    return (round(l * 100), sa, sb, 0)


class Readers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_acb_lab(self):
        path = self.root / "book.acb"
        write_acb(path, {k[:-2]: v for k, v in BOOK.items()})
        title, colors = colorbooks.read_any(path)
        self.assertEqual(title, "TEST Solid Coated")
        self.assertEqual(len(colors), len(BOOK))                      # empty slot skipped
        by_code = {c.code: c for c in colors}
        self.assertEqual(set(by_code), set(BOOK))
        self.assertEqual(by_code["0001 C"].name, "PANTONE 0001 C")
        for code, hex_c in BOOK.items():                              # Lab bytes quantize a bit
            self.assertLess(cl.delta_e(by_code[code].hex, hex_c), 1.5, code)

    def test_acb_rgb_and_cmyk(self):
        rgb = self.root / "rgb.acb"
        write_acb(rgb, {"0001": "#0A4A90"}, ctype=0)
        self.assertEqual(colorbooks.read_any(rgb)[1][0].hex, "#0A4A90")
        cmyk = self.root / "cmyk.acb"
        write_acb(cmyk, {"0001": "#0A4A90"}, ctype=2)
        color = colorbooks.read_any(cmyk)[1][0]
        self.assertEqual((color.model, color.lab), ("CMYK", None))

    def test_aco_named(self):
        path = self.root / "s.aco"
        write_aco(path, [
            ("PANTONE 0001 C", 0, (0x0A0A, 0x4A4A, 0x9090, 0)),
            ("PANTONE 0002 C", 7, aco_lab("#D2331F")),
            ("PANTONE 0003 C", 1, (round(54 / 360 * 65536), round(0.6 * 65535), round(0.96 * 65535), 0)),
            ("PANTONE Test Black C", 2, (0, 0, 0, 0)),
        ])
        _, colors = colorbooks.read_any(path)
        self.assertEqual([c.code for c in colors], ["0001 C", "0002 C", "0003 C", "Test Black C"])
        self.assertEqual(colors[0].hex, "#0A4A90")
        self.assertLess(cl.delta_e(colors[1].hex, "#D2331F"), 0.5)
        self.assertEqual(colors[2].model, "HSB")
        self.assertIsNone(colors[3].lab)

    def test_aco_stray_terminator_zero(self):
        path = self.root / "z.aco"
        write_aco(path, [(" PANTONE Test Yellow 12 C0", 0, (65535, 55000, 0, 0)),
                         (" PANTONE Test Red C0", 0, (65000, 14000, 7000, 0))])
        self.assertEqual([c.code for c in colorbooks.read_any(path)[1]], ["Test Yellow 12 C", "Test Red C"])
        mixed = self.root / "m.aco"                        # legit names keep their digits
        write_aco(mixed, [("PANTONE 0001 C", 0, (0, 0, 0, 0)), ("PANTONE 0005", 0, (0, 0, 0, 0))])
        self.assertEqual([c.code for c in colorbooks.read_any(mixed)[1]][1], "0005")

    def test_aco_unnamed_v1(self):
        path = self.root / "v1.aco"
        write_aco(path, [("x", 0, (65535, 0, 0, 0))], named=False)
        self.assertEqual(colorbooks.read_any(path)[1][0].name, "Swatch 1")

    def test_ase_book_and_unknown_format(self):
        path = self.root / "b.ase"
        l, a, b = cl.to_lab_d50("#0A4A90")
        ase.write_ase(path, [("PANTONE 0001 C", "LAB", (l / 100, a, b))])
        self.assertEqual(colorbooks.read_any(path)[1][0].hex, "#0A4A90")
        bad = self.root / "x.acbl"
        bad.write_text("<xml/>")
        with self.assertRaises(colorbooks.ColorBookError):
            colorbooks.read_any(bad)


class LibraryAndMatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.lib_dir = self.root / "pantone/libraries"
        self.book = self.root / "solid.acb"
        write_acb(self.book, {k[:-2]: v for k, v in BOOK.items()})

    def tearDown(self):
        self.tmp.cleanup()

    def test_index_lookup_and_nearest(self):
        name, stats = library.add_library(self.book, self.lib_dir)
        self.assertEqual((name, stats["colors"], stats["skipped"]), ("TEST Solid Coated", 6, 0))
        self.assertTrue((self.lib_dir / "source/solid.acb").exists())
        libs = library.load_libraries(self.lib_dir)
        self.assertEqual(library.lookup_code("0001  c", libs)[0][1].code, "0001 C")
        # a slightly off screenshot blue still lands on 0001 C
        hits = library.nearest("#0A4F9A", libs, top=2)
        self.assertEqual(hits[0][1].code, "0001 C")
        self.assertEqual(library.grade(hits[0][2]), "close" if hits[0][2] > 2 else "match")
        self.assertEqual(library.grade(30), "far")
        with self.assertRaises(KeyError):
            library.nearest("#000000", libs, library="nope")

    def test_out_of_gamut_compares_unclipped(self):
        vivid = self.root / "vivid.acb"
        out = b"8BCB" + struct.pack(">HH", 1, 1) + b"".join(_ustr(s) for s in ("V", "PANTONE ", " C", ""))
        rec = _ustr("0007") + b"0007  " + bytes([round(88 * 2.55), 128 - 90, 128 + 80])  # very green
        vivid.write_bytes(out + struct.pack(">HHHH", 1, 1, 1, 7) + rec)
        _, colors = colorbooks.read_any(vivid)
        self.assertFalse(colors[0].in_gamut)
        library.add_library(vivid, self.lib_dir)
        libs = library.load_libraries(self.lib_dir)
        self.assertEqual(library.nearest(colors[0].hex, libs)[0][1].code, "0007 C")

    def test_cli_flow(self):
        reg = self.root / "pantone/swatches.json"
        env = {"PAPER_COLORS_SWATCHES": str(reg)}
        out = io.StringIO()
        with mock.patch.dict(os.environ, env), redirect_stdout(out):
            self.assertEqual(paper_colors.main(["swatch", "library", "add", str(self.book)]), 0)
            self.assertEqual(paper_colors.main(["swatch", "match", "#0A4F9A", "0002 C"]), 0)
            self.assertEqual(paper_colors.main(["swatch", "add", "0001 C", "--from-library"]), 0)
            self.assertEqual(paper_colors.main(["swatch", "add", "9999 C", "--from-library"]), 2)
            # same code in a second book -> must choose
            other = self.root / "other.acb"
            write_acb(other, {"0001": "#0A4A90"}, title="Other Book")
            paper_colors.main(["swatch", "library", "add", str(other)])
            self.assertEqual(paper_colors.main(["swatch", "add", "0001 C", "--from-library"]), 2)
            self.assertEqual(paper_colors.main(["swatch", "add", "0002 C", "--from-library",
                                                "--library", "TEST Solid Coated"]), 0)
        text = out.getvalue()
        self.assertIn("exact -> 0002 C", text)
        self.assertIn("0001 C", text)
        reg_data = registry.load_swatches(reg)
        self.assertEqual(reg_data["0001 C"]["method"], "library")
        self.assertEqual(reg_data["0002 C"]["source"], "TEST Solid Coated")

    @unittest.skipIf(Image is None, "Pillow not installed")
    def test_match_screenshot(self):
        library.add_library(self.book, self.lib_dir)
        shot = self.root / "palette.png"
        img = Image.new("RGB", (600, 200), (255, 255, 255))
        img.paste(tuple(round(c * 255) for c in cl.parse_hex("#05509A")), (20, 20, 180, 180))
        img.paste(tuple(round(c * 255) for c in cl.parse_hex("#DC2B1E")), (220, 20, 380, 180))
        img.save(shot)
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"PAPER_COLORS_SWATCHES": str(self.root / "pantone/swatches.json")}), \
                redirect_stdout(out):
            self.assertEqual(paper_colors.main(["swatch", "match", str(shot), "--top", "1"]), 0)
        lines = out.getvalue().splitlines()
        firsts = [lines[i + 1] for i, ln in enumerate(lines) if ln.startswith("#")]
        self.assertTrue(any("0001 C" in ln for ln in firsts), out.getvalue())
        self.assertTrue(any("0002 C" in ln for ln in firsts), out.getvalue())


if __name__ == "__main__":
    unittest.main()
