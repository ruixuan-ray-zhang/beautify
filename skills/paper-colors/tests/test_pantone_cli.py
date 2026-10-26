"""pantone-cli match index -> libraries, and book use/medium metadata.
The index here is synthetic (invented codes), in pantone-cli's schemaVersion 1 shape."""

import gzip
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import books  # noqa: E402
import colorlib as cl  # noqa: E402
import library  # noqa: E402
import paper_colors  # noqa: E402
import pantone_cli  # noqa: E402


def _color(code, hex_c, book="testCoated"):
    l, a, b = cl.to_lab_d50(hex_c)
    return {"code": code, "name": code.title(), "hex": hex_c.lstrip("#"),
            "lab": {"l": l, "a": a, "b": b}, "bookId": book}


def synthetic_index() -> dict:
    return {
        "meta": {"schemaVersion": 1, "indexedAt": "2026-01-01T00:00:00Z", "colorCount": 4,
                 "relationshipCount": 1},
        "books": [
            {"id": "testCoated", "title": "Test Solid Coated", "group": "Test",
             "info": {"en": {"target": "Testing", "description": "Synthetic ink on coated paper"}}},
            {"id": "testCotton", "title": "Test Cotton TCX", "group": "Test", "info": {"en": {}}},
        ],
        "bookVersions": {},
        "colorsByBook": {
            "testCoated": [_color("TEST 1 C", "#1F4E99"), _color("TEST 2 C", "#E0703A"),
                           _color("TEST 3 C", "#99BBDD"), {"code": "NOCOLOR C"}],
            "testCotton": [_color("00-1111 TCX", "#CCAA88", "testCotton")],
        },
        "relationshipsByColor": {
            "testCoated\x1fTEST 1 C": {
                "bookId": "testCoated", "code": "TEST 1 C",
                "shades": {"lightness": [{"bookId": "testCoated", "code": "TEST 3 C"}]},
                "harmonies": {"COMPLEMENTARY": [{"bookId": "testCoated", "code": "TEST 2 C"}],
                              "BOGUS": [{"bookId": "testCoated", "code": "TEST 3 C"}]}},
        },
    }


class BooksTest(unittest.TestCase):
    def test_known_names(self):
        self.assertEqual(books.describe("PANTONE® Solid Coated-V5")["id"], "pantoneSolidCoated")
        self.assertEqual(books.describe("PANTONE+ Solid Uncoated")["id"], "pantoneSolidUncoated")
        self.assertEqual(books.describe("PANTONE Color Bridge Coated")["id"], "pantoneColorBridgeCoated")
        self.assertEqual(books.describe("PANTONE® F+H cotton TCX")["id"], "pantoneFhCottonTcx")
        self.assertEqual(books.describe("PANTONE FHI Paper TPG")["id"], "pantoneFhiPaperTpg")
        self.assertIn("screen", books.describe("PANTONE Metallics Coated")["note"])

    def test_unknown_name(self):
        self.assertIsNone(books.describe("My Brand Swatches"))

    def test_pantone_cli_summary_falls_back_to_name(self):
        meta = books.from_pantone_cli({"id": "x", "title": "Test Cotton TCX", "info": {"en": {}}})
        self.assertEqual(meta["medium"], "Dye on cotton fabric")


class PantoneCliIndexTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.index = self.root / "pantone-match-index.json"
        self.index.write_text(json.dumps(synthetic_index()))
        self.lib_dir = self.root / "libraries"

    def tearDown(self):
        self.tmp.cleanup()

    def test_find_index_order(self):
        cli_home = self.root / "clihome"
        cli_home.mkdir()
        (cli_home / pantone_cli.INDEX_NAME).write_text("{}")
        with mock.patch.dict(os.environ, {"PANTONE_CLI_HOME": str(cli_home)}, clear=False):
            os.environ.pop("PANTONE_INDEX", None)
            self.assertEqual(pantone_cli.find_index(None), cli_home / pantone_cli.INDEX_NAME)
            with mock.patch.dict(os.environ, {"PANTONE_INDEX": str(self.index)}):
                self.assertEqual(pantone_cli.find_index(None), self.index)
            self.assertEqual(pantone_cli.find_index(str(self.index)), self.index)

    def test_missing_index_explains_how_to_get_one(self):
        with mock.patch.dict(os.environ, {"PANTONE_CLI_HOME": str(self.root / "none")}):
            os.environ.pop("PANTONE_INDEX", None)
            with self.assertRaisesRegex(ValueError, "pantone-cli export"):
                pantone_cli.find_index(str(self.root / "missing.json"))

    def test_rejects_other_json_and_reads_gzip(self):
        other = self.root / "other.json"
        other.write_text('{"meta": {"schemaVersion": 2}}')
        with self.assertRaisesRegex(ValueError, "schemaVersion"):
            pantone_cli.load_index(other)
        gz = self.root / "index.json.gz"
        gz.write_bytes(gzip.compress(self.index.read_bytes()))
        self.assertIn("testCoated", pantone_cli.load_index(gz)["colorsByBook"])

    def test_damaged_gzip_is_a_clean_error(self):
        bad = self.root / "bad.json.gz"
        bad.write_bytes(gzip.compress(self.index.read_bytes())[:40])
        with self.assertRaisesRegex(ValueError, "damaged gzip"):
            pantone_cli.load_index(bad)

    def test_same_title_books_do_not_overwrite(self):
        data = synthetic_index()
        data["books"][1]["title"] = data["books"][0]["title"]
        self.index.write_text(json.dumps(data))
        added = library.add_pantone_cli(self.index, self.lib_dir)
        self.assertEqual(len(library.load_libraries(self.lib_dir)), 2)
        self.assertEqual(len({n for n, _ in added}), 2)

    def test_books_become_libraries_with_meta_and_relationships(self):
        added = library.add_pantone_cli(self.index, self.lib_dir)
        self.assertEqual([n for n, _ in added], ["Test Solid Coated", "Test Cotton TCX"])
        self.assertEqual(added[0][1]["skipped"], 1)               # the entry without a color
        libs = library.load_libraries(self.lib_dir)
        c = next(c for c in libs["Test Solid Coated"] if c.code == "TEST 1 C")
        self.assertEqual(c.hex, "#1F4E99")
        self.assertLess(cl.delta_e_lab(c.lab, cl.to_lab("#1F4E99")), 0.05)  # D50 Lab adapted to D65
        meta = library.load_meta(self.lib_dir)
        self.assertEqual(meta["Test Solid Coated"]["book"]["medium"], "Synthetic ink on coated paper")
        rel = meta["Test Solid Coated"]["relationships"]["TEST 1 C"]
        self.assertEqual(rel["harmonies"], {"COMPLEMENTARY": ["TEST 2 C"]})   # unknown kinds dropped
        self.assertEqual(rel["shades"], {"lightness": ["TEST 3 C"]})
        self.assertFalse(list(self.lib_dir.glob("source/*")))      # the index is not copied

    def test_select_books(self):
        added = library.add_pantone_cli(self.index, self.lib_dir, ["testCotton"])
        self.assertEqual([n for n, _ in added], ["Test Cotton TCX"])
        with self.assertRaisesRegex(ValueError, "unknown book"):
            library.add_pantone_cli(self.index, self.lib_dir, ["nope"])

    def test_cli_add_books_and_list_json(self):
        env = {"PAPER_COLORS_SWATCHES": str(self.root / "swatches.json")}
        with mock.patch.dict(os.environ, env):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(paper_colors.main(["swatch", "library", "books", "--index", str(self.index), "--json"]), 0)
            self.assertEqual([b["id"] for b in json.loads(buf.getvalue())["books"]], ["testCoated", "testCotton"])
            with redirect_stdout(io.StringIO()):
                self.assertEqual(paper_colors.main(["swatch", "library", "add", str(self.index)]), 0)
            buf = io.StringIO()
            with redirect_stdout(buf):
                paper_colors.main(["swatch", "library", "list", "--json"])
            rows = {r["name"]: r for r in json.loads(buf.getvalue())}
            self.assertEqual(rows["Test Solid Coated"]["relationships"], 1)
            self.assertEqual(rows["Test Cotton TCX"]["book"]["medium"], "Dye on cotton fabric")


if __name__ == "__main__":
    unittest.main()
