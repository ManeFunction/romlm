import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import archives
from archives import ExtractMode


def make_zip(path, *names):
    with zipfile.ZipFile(path, "w") as z:
        for name in names:
            z.writestr(name, "data")
    return path


class GenericNameTest(unittest.TestCase):
    def test_generic_names_of_disc_and_disk_dumps(self):
        for name in ("game.iso", "GAME.CUE", "Disc 1.cue", "disc2.chd", "disk1.adf", "Disk 1A.adf", "CD2.bin",
                     "cd_1.img", "track01.bin", "Track 03.raw", "Disk 1 Side A.st", "Side B.st", "Disc 1 of 2.chd",
                     "EBOOT.BIN", "default.xbe", "main.dol", "boot.bin", "image.img", "rom.bin", "01.bin",
                     "game.nkit.iso", "dvd1.iso", "gdrom.gdi", "umd.iso"):
            with self.subTest(name=name):
                self.assertTrue(archives.is_generic_name(name))

    def test_game_names_are_not_generic(self):
        for name in ("Zelda (USA).nes", "Final Fantasy VII (USA) (Disc 1).cue", "Disco Elysium.iso", "games.iso",
                     "diska.adf", "Vol. 1 (USA).bin", "Super Mario Bros. 3 (USA).nes", "1942.nes", "a.iso",
                     "Game (USA)", "Gamé.iso", ""):
            with self.subTest(name=name):
                self.assertFalse(archives.is_generic_name(name))

    def test_generic_folder_names(self):
        self.assertTrue(archives.is_generic_name("Disc 1"))
        self.assertFalse(archives.is_generic_name("Game (USA)"))

    def test_strip_extensions(self):
        self.assertEqual(archives.strip_extensions("game.nkit.iso"), "game")
        self.assertEqual(archives.strip_extensions("Game Vol. 1 (USA).bin"), "Game Vol. 1 (USA)")
        self.assertEqual(archives.strip_extensions("Disc 1"), "Disc 1")


class ContentsTest(unittest.TestCase):
    def test_top_level_entries_skip_system_junk(self):
        entries = ["Game/", "Game/track01.bin", "./Game/track02.raw", "__MACOSX/._Game", ".DS_Store", "Thumbs.db"]
        self.assertEqual(archives.top_level_entries(entries), {"Game"})

    def test_own_folder_is_needed_for_many_entries_or_a_generic_one(self):
        self.assertFalse(archives.needs_own_folder(set()))
        self.assertFalse(archives.needs_own_folder({"Zelda (USA).nes"}))
        self.assertFalse(archives.needs_own_folder({"Zelda (USA)"}))
        self.assertTrue(archives.needs_own_folder({"Game (USA).cue", "Game (USA).bin"}))
        self.assertTrue(archives.needs_own_folder({"game.iso"}))
        self.assertTrue(archives.needs_own_folder({"Disc 1"}))

    def test_own_folder_name(self):
        self.assertEqual(archives.own_folder_name("A/Game (USA).zip", {"game.iso"}), "Game (USA)")
        self.assertEqual(archives.own_folder_name("Game Vol. 1 (USA).7z", {"a", "b"}), "Game Vol. 1 (USA)")
        # romlm packs "Game.nes" into "Game.nes.zip"
        self.assertEqual(archives.own_folder_name("Game (USA).nes.zip", {"Game (USA).nes"}), "Game (USA)")


class ExtractionFolderTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.single = make_zip(os.path.join(self.folder.name, "Zelda (USA).zip"), "Zelda (USA).nes")
        self.generic = make_zip(os.path.join(self.folder.name, "Saturn Game (USA).zip"), "game.iso")
        self.many = make_zip(os.path.join(self.folder.name, "PS Game (USA).zip"), "PS Game (USA).cue",
                             "PS Game (USA).bin")

    def test_plain_mode_does_not_read_the_archive(self):
        missing = os.path.join(self.folder.name, "Missing.zip")
        self.assertEqual(archives.extraction_folder(missing, "out", ExtractMode.PLAIN), "out")

    def test_folders_mode_always_makes_a_folder(self):
        self.assertEqual(archives.extraction_folder(self.single, "out", ExtractMode.FOLDERS),
                         os.path.join("out", "Zelda (USA)"))
        self.assertEqual(archives.extraction_folder(self.many, "", ExtractMode.FOLDERS), "PS Game (USA)")

    def test_auto_mode_makes_a_folder_only_when_needed(self):
        self.assertEqual(archives.extraction_folder(self.single, "out", ExtractMode.AUTO), "out")
        self.assertEqual(archives.extraction_folder(self.generic, "out", ExtractMode.AUTO),
                         os.path.join("out", "Saturn Game (USA)"))
        self.assertEqual(archives.extraction_folder(self.many, "out", ExtractMode.AUTO),
                         os.path.join("out", "PS Game (USA)"))

    def test_auto_mode_keeps_a_named_folder_inside_the_archive(self):
        archive = make_zip(os.path.join(self.folder.name, "DC Game (USA).zip"),
                           "DC Game (USA)/disc.gdi", "DC Game (USA)/track01.bin")
        self.assertEqual(archives.extraction_folder(archive, "", ExtractMode.AUTO), "")


@unittest.skipUnless(archives.find_seven_zip_binary(), "7-Zip is not installed")
class SevenZipContentsTest(unittest.TestCase):
    def test_lists_7z_entries(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "src", "Game"))
            for name in ("Game/track01.bin", "Game/track02.raw", "disc.gdi"):
                with open(os.path.join(root, "src", name), "w") as f:
                    f.write("data")
            archive = os.path.join(root, "DC Game (USA).7z")
            subprocess.run([archives.find_seven_zip_binary(), "a", archive, "Game", "disc.gdi"],
                           cwd=os.path.join(root, "src"), check=True, capture_output=True)
            self.assertEqual(sorted(archives.list_entries(archive)),
                             ["Game", "Game/track01.bin", "Game/track02.raw", "disc.gdi"])
            self.assertEqual(archives.extraction_folder(archive, "", ExtractMode.AUTO), "DC Game (USA)")


if __name__ == "__main__":
    unittest.main()
