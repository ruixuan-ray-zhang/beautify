"""The data folder lives outside the skill ($PAPER_COLORS_HOME), and `init` never overwrites."""

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

import paper_colors  # noqa: E402
import paths  # noqa: E402

CLEAN = {k: v for k, v in os.environ.items()
         if k not in ("PAPER_COLORS_SWATCHES", "PAPER_COLORS_PALETTES")}


class DataHomeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "data"
        self.env = mock.patch.dict(os.environ, {**CLEAN, "PAPER_COLORS_HOME": str(self.home)}, clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_defaults_sit_in_home_not_in_skill(self):
        self.assertEqual(paths.swatches(), self.home / "swatches.json")
        self.assertEqual(paths.data_dir("libraries"), self.home / "libraries")
        self.assertNotIn(str(paths.SKILL_DIR), str(paths.swatches()))

    def test_palettes_fall_back_to_template_until_init(self):
        self.assertEqual(paths.palettes(), paths.TEMPLATE_PALETTES)
        paths.init()
        self.assertEqual(paths.palettes(), self.home / "palettes.json")
        self.assertTrue((self.home / "inbox" / "README.md").exists())

    def test_init_never_overwrites(self):
        paths.init()
        (self.home / "palettes.json").write_text('{"themes": {"mine": {}}}')
        paths.init()
        self.assertIn("mine", json.loads((self.home / "palettes.json").read_text())["themes"])

    def test_init_from_old_skill_folder(self):
        old = Path(self.tmp.name) / "old-skill"
        (old / "pantone" / "libraries").mkdir(parents=True)
        (old / "pantone" / "swatches.json").write_text('{"X 1 C": {"hex": "#112233"}}')
        (old / "pantone" / "libraries" / "book.json").write_text("{}")
        (old / "palettes.json").write_text('{"themes": {"old": {}}}')
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(paper_colors.main(["init", "--from", str(old)]), 0)
        self.assertTrue((self.home / "libraries" / "book.json").exists())
        self.assertIn("old", json.loads((self.home / "palettes.json").read_text())["themes"])
        self.assertIn("#112233", (self.home / "swatches.json").read_text())

    def test_init_from_after_plain_init_still_brings_themes(self):
        paths.init()                                   # the README's order: init, then --from
        old = Path(self.tmp.name) / "old-skill"
        (old / "pantone").mkdir(parents=True)
        (old / "palettes.json").write_text('{"themes": {"old": {}}}')
        paths.init(old)
        self.assertIn("old", json.loads((self.home / "palettes.json").read_text())["themes"])

    def test_init_from_folder_without_palettes_keeps_template(self):
        old = Path(self.tmp.name) / "bare"
        old.mkdir()
        paths.init(old)
        self.assertEqual(paths.palettes(), self.home / "palettes.json")

    def test_swatches_override_moves_data_folders_with_it(self):
        other = Path(self.tmp.name) / "other" / "sw.json"
        with mock.patch.dict(os.environ, {"PAPER_COLORS_SWATCHES": str(other)}):
            paths.init()
            self.assertTrue((other.parent / "inbox").is_dir())

    def test_unknown_data_folder(self):
        with self.assertRaises(KeyError):
            paths.data_dir("cache")

    def test_where_names_template(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            paper_colors.main(["where"])
        self.assertIn("bundled template", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
