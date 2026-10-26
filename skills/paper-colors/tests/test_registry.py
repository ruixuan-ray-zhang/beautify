"""Pantone registry + screenshot sampling.

The sampling test needs Pillow:  uv run --with pillow python -m unittest discover -s tests
"""

import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import colorlib as cl  # noqa: E402
import registry  # noqa: E402

try:
    from PIL import Image
except ImportError:
    Image = None

# Display P3 (D65) primaries, Bradford-adapted to D50, as Apple ships them.
P3_COLORANTS = {"rXYZ": (0.515121, 0.241196, -0.001053),
                "gXYZ": (0.291977, 0.692245, 0.041885),
                "bXYZ": (0.157104, 0.066574, 0.784073)}
P3_TO_XYZ = ((0.4865709, 0.2656677, 0.1982173),
             (0.2289746, 0.6917385, 0.0792869),
             (0.0000000, 0.0451134, 1.0439444))
SRGB_TO_XYZ = ((0.4124564, 0.3575761, 0.1804375),
               (0.2126729, 0.7151522, 0.0721750),
               (0.0193339, 0.1191920, 0.9503041))


def _s15(v):
    return struct.pack(">i", round(v * 65536))


def _p3_icc() -> bytes:
    """Minimal ICC v2 matrix/TRC profile for Display P3 (sRGB transfer curve)."""
    desc_text = b"Display P3 (test)\x00"
    desc = (b"desc" + b"\0" * 4 + struct.pack(">I", len(desc_text)) + desc_text
            + b"\0" * 8 + b"\0" * 3 + b"\0" * 67)
    para = (b"para" + b"\0" * 4 + struct.pack(">HH", 3, 0)
            + b"".join(_s15(v) for v in (2.4, 1 / 1.055, 0.055 / 1.055, 1 / 12.92, 0.04045)))
    xyz = lambda v: b"XYZ " + b"\0" * 4 + b"".join(_s15(c) for c in v)  # noqa: E731
    tags = [(b"desc", desc), (b"wtpt", xyz((0.9642, 1.0, 0.8249))),
            *[(k.encode(), xyz(v)) for k, v in P3_COLORANTS.items()],
            (b"rTRC", para), (b"gTRC", para), (b"bTRC", para)]
    offset = 128 + 4 + 12 * len(tags)
    table, data = b"", b""
    for sig, body in tags:
        body += b"\0" * (-len(body) % 4)
        table += sig + struct.pack(">II", offset + len(data), len(body))
        data += body
    size = offset + len(data)
    header = (struct.pack(">I", size) + b"\0" * 4 + bytes([2, 0x10, 0, 0]) + b"mntrRGB XYZ "
              + b"\0" * 12 + b"acsp" + b"\0" * 24 + struct.pack(">I", 0)
              + _s15(0.9642) + _s15(1.0) + _s15(0.8249) + b"\0" * 48)
    assert len(header) == 128
    return header + struct.pack(">I", len(tags)) + table + data


def _inv3(m):
    (a, b, c), (d, e, f), (g, h, i) = m
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return ((e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det), \
           ((f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det), \
           ((d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det)


def _mul(m, v):
    return tuple(sum(x * y for x, y in zip(row, v)) for row in m)


def srgb_hex_to_p3_bytes(hex_color):
    lin = [cl._to_linear(c) for c in cl.parse_hex(hex_color)]
    p3 = _mul(_inv3(P3_TO_XYZ), _mul(SRGB_TO_XYZ, lin))
    return tuple(round(cl._to_gamma(c) * 255) for c in p3)


class Registry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "swatches.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_and_reload(self):
        shot = self.root / "inbox.png"
        shot.write_bytes(b"x")
        entry = registry.add_swatch("00-0001  TCX", "Test Blue", "#174A7C", "#0F4D82", shot,
                                   path=self.path, archive=self.root / "screenshots")
        self.assertEqual(entry["hex"], "#174A7C")
        self.assertEqual(entry["method"], "transcribed")
        self.assertFalse(shot.exists())                       # moved to archive
        self.assertTrue((self.root / "screenshots/00-0001-tcx.png").exists())
        self.assertIn("00-0001 TCX", registry.load_swatches(self.path))

    def test_sampled_only(self):
        entry = registry.add_swatch("0001 C", "", None, "#0A4A90", None, path=self.path)
        self.assertEqual(entry["method"], "sampled")

    def test_disagreeing_readings_rejected(self):
        with self.assertRaises(ValueError):
            registry.add_swatch("0001 C", "", "#0A4A90", "#C04C97", None, path=self.path)
        self.assertEqual(registry.load_swatches(self.path), {})

    def test_bad_input(self):
        for code, hex_c, sampled in (("", "#000000", None), ("0001 C", None, None),
                                     ("0001 C", "#12", None)):
            with self.assertRaises(ValueError):
                registry.add_swatch(code, "", hex_c, sampled, None, path=self.path)


@unittest.skipIf(Image is None, "Pillow not installed")
class Sampling(unittest.TestCase):
    def test_p3_screenshot_recovers_srgb(self):
        target = "#174A7C"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shot.png"
            img = Image.new("RGB", (400, 300), (255, 255, 255))
            img.paste(srgb_hex_to_p3_bytes(target), (40, 40, 240, 200))   # the swatch
            img.paste((30, 30, 30), (260, 40, 380, 60))                    # some "text"
            img.save(path, icc_profile=_p3_icc())
            colors, profile, _ = registry.dominant_colors(path)
        self.assertIn("P3", profile)
        swatch = next(c for c in colors if not c["near_white"])
        self.assertLess(cl.delta_e(swatch["hex"], target), 1.0, swatch)
        x0, y0, x1, y1 = swatch["bbox"]
        self.assertTrue(35 <= x0 <= 45 and 195 <= y1 <= 200, swatch["bbox"])

    def test_untagged_is_srgb(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shot.png"
            Image.new("RGB", (50, 50), (178, 44, 76)).save(path)
            colors, profile, _ = registry.dominant_colors(path)
        self.assertIn("assumed sRGB", profile)
        self.assertEqual(colors[0]["hex"], "#B22C4C")


if __name__ == "__main__":
    unittest.main()
