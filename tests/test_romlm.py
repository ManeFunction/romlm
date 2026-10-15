import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import romlm
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

    def test_duplicates_action_depends_on_log(self):
        self.assertEqual(self.parse("-r").remove_duplicates_action, Action.KEEP_ALL)
        self.assertEqual(self.parse("-r", "-l").remove_duplicates_action, Action.ASK)
        self.assertEqual(self.parse("-r", "one", "-l").remove_duplicates_action, Action.KEEP_ONE)

    def test_lists(self):
        options = self.parse("-s", "f", "-f", "Japan,Europe", "-e", "USA")
        self.assertEqual(options.subfolders, ["Japan", "Europe"])
        self.assertEqual(options.exclude_tags, ["USA"])

    def test_mistakes_are_usage_errors(self):
        for args in (["-p", "rar"], ["-r", "bogus"], ["-u", "pirates"], ["-s", "x"], ["-x", "-p"], ["--nope"]):
            with self.subTest(args=args), mock.patch("sys.stderr"), self.assertRaises(SystemExit) as raised:
                self.parse(*args)
            self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
