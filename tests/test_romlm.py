import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import romlm
from archives import ExtractMode
from duplicates import Action
from romlm import CategoryOption as C


def folder(filename, separation=C.HOMEBREW | C.PIRATES, sort=C(0), subfolders=None, excludes=None):
    return romlm.get_new_folder(filename, separation, sort, subfolders, excludes)


class GetNewFolderTest(unittest.TestCase):
    def test_lettered_folders(self):
        self.assertEqual(folder("Zelda (USA).nes"), "Z")
        self.assertEqual(folder("1942 (USA).nes"), "1-9")
        self.assertEqual(folder("[BIOS] Sega CD (USA).bin"), "!!BIOS")

    def test_homebrew_and_pirates_are_separated(self):
        self.assertEqual(folder("Game (Homebrew).nes"), "!Homebrew")
        self.assertEqual(folder("Game (Unl).nes"), "!Pirates")

    def test_separation_can_be_limited(self):
        self.assertEqual(folder("Game (Homebrew).nes", separation=C.PIRATES), "G")
        self.assertEqual(folder("Game (Unl).nes", separation=C(0)), "G")

    def test_special_folders_can_be_sorted_too(self):
        self.assertEqual(folder("Game (Homebrew).nes", sort=C.HOMEBREW), "!Homebrew/G")
        self.assertEqual(folder("Game (Unl).nes", sort=C.PIRATES), "!Pirates/G")

    def test_user_defined_folders(self):
        self.assertEqual(folder("Game (Japan).nes", subfolders=["Japan"]), "!Japan")
        self.assertEqual(folder("Game (Japan).nes", sort=C.SUBFOLDERS, subfolders=["japan"]), "!japan/G")
        self.assertEqual(folder("Japan Game (USA).nes", subfolders=["Japan"]), "J")

    def test_excluded_tags_skip_the_user_defined_folders(self):
        self.assertEqual(folder("Game (Japan, USA).nes", subfolders=["Japan"], excludes=["usa"]), "G")

    def test_does_not_touch_the_disk(self):
        with mock.patch("os.makedirs") as makedirs:
            folder("Game (USA).nes")
        makedirs.assert_not_called()


class RemoveEmptySubfoldersTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = self.folder.name

    def make(self, *paths):
        for path in paths:
            full = os.path.join(self.root, path)
            if path.endswith("/"):
                os.makedirs(full, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(full), exist_ok=True)
                open(full, "w").close()

    def folders(self):
        return sorted(os.path.relpath(d, self.root) for d, _, _ in os.walk(self.root))

    def clean(self, is_log_enabled=False):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            romlm.remove_empty_subfolders(self.root, is_log_enabled)
        return output.getvalue()

    def test_removes_whole_empty_trees(self):
        self.make("a/b/c/", "a/d/", "keep/Game (USA).nes")
        self.clean()
        self.assertEqual(self.folders(), [".", "keep"])

    def test_keeps_folders_with_files_and_their_parents(self):
        self.make("a/b/Game (USA).nes", "a/c/", "d/.hidden")
        self.clean()
        self.assertEqual(self.folders(), [".", "a", "a/b", "d"])

    def test_keeps_the_root_even_if_it_ends_up_empty(self):
        self.make("a/b/")
        self.clean()
        self.assertTrue(os.path.isdir(self.root))
        self.assertEqual(os.listdir(self.root), [])

    def test_logs_each_removed_folder_children_first(self):
        self.make("a/b/")
        lines = self.clean(True).splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].endswith(os.path.join("a", "b") + "\x1b[0m"))
        self.assertTrue(lines[1].endswith("a\x1b[0m"))
        self.assertEqual(self.clean(False), "")


class ParseOptionsTest(unittest.TestCase):
    def parse(self, *args):
        return romlm.parse_options(list(args))

    def test_defaults(self):
        options = self.parse()
        self.assertEqual(options.input_folder, ".")
        self.assertFalse(options.is_sort_enabled)
        self.assertFalse(options.is_remove_duplicates)
        self.assertEqual(options.separation_options, C.HOMEBREW | C.PIRATES)
        self.assertEqual(options.packing_format, "7z")

    def test_sort_options(self):
        self.assertEqual(self.parse("-s").sort_options, C(0))
        self.assertTrue(self.parse("-s").is_sort_enabled)
        self.assertEqual(self.parse("-s", "hp").sort_options, C.HOMEBREW | C.PIRATES)
        self.assertEqual(self.parse("-s", "a").sort_options, C.HOMEBREW | C.PIRATES | C.SUBFOLDERS)
        self.assertEqual(self.parse("-s", "none").sort_options, C(0))
        self.assertTrue(self.parse("-s", "reverse").is_reverse_sort)
        self.assertFalse(self.parse("-s", "hp").is_reverse_sort)

    def test_unlicensed_options(self):
        self.assertEqual(self.parse("-u", "h").separation_options, C.HOMEBREW)
        self.assertEqual(self.parse("-u", "p").separation_options, C.PIRATES)
        self.assertEqual(self.parse("-u", "none").separation_options, C(0))
        self.assertEqual(self.parse("-u").separation_options, C(0))

    def test_pack_format(self):
        self.assertTrue(self.parse("-p").is_packing_enabled)
        self.assertEqual(self.parse("-p").packing_format, "7z")
        self.assertEqual(self.parse("-p", "zip").packing_format, "zip")

    def test_extract_mode(self):
        self.assertFalse(self.parse().is_unpacking_enabled)
        self.assertTrue(self.parse("-x").is_unpacking_enabled)
        self.assertEqual(self.parse("-x").extract_mode, ExtractMode.AUTO)
        self.assertEqual(self.parse("-x", "-l").extract_mode, ExtractMode.AUTO)
        self.assertEqual(self.parse("-x", "f").extract_mode, ExtractMode.FOLDERS)
        self.assertEqual(self.parse("--extract", "p").extract_mode, ExtractMode.PLAIN)

    def test_duplicates_action_depends_on_log(self):
        self.assertEqual(self.parse("-r").remove_duplicates_action, Action.KEEP_ALL)
        self.assertEqual(self.parse("-r", "-l").remove_duplicates_action, Action.ASK)
        self.assertEqual(self.parse("-r", "one", "-l").remove_duplicates_action, Action.KEEP_ONE)

    def test_dry_run_implies_log_but_not_asking(self):
        options = self.parse("-r", "-n")
        self.assertTrue(options.is_dry_run)
        self.assertTrue(options.is_log_enabled)
        self.assertEqual(options.remove_duplicates_action, Action.KEEP_ALL)
        self.assertFalse(self.parse("-r").is_dry_run)

    def test_lists(self):
        options = self.parse("-s", "f", "-f", "Japan,Europe", "-e", "USA")
        self.assertEqual(options.subfolders, ["Japan", "Europe"])
        self.assertEqual(options.exclude_tags, ["USA"])

    def test_mistakes_are_usage_errors(self):
        for args in (["-p", "rar"], ["-r", "bogus"], ["-u", "pirates"], ["-s", "x"], ["-x", "-p"], ["-x", "a"],
                     ["--nope"]):
            with self.subTest(args=args), mock.patch("sys.stderr"), self.assertRaises(SystemExit) as raised:
                self.parse(*args)
            self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
