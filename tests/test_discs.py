import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import discs


def game_folders(*files):
    return discs.find_game_folders([os.path.join(*f.split("/")) for f in files])


class IsGameFolderTest(unittest.TestCase):
    def test_disc_sheets_with_their_tracks(self):
        for files in (["Game (USA).cue", "Game (USA).bin"], ["Game (USA).cue", "Game (USA).iso"],
                      ["Game (USA).cue", "Game (USA) (Track 01).bin", "Game (USA) (Track 02).bin"],
                      ["Game (USA).ccd", "Game (USA).img", "Game (USA).sub"], ["Game (USA).mds", "Game (USA).mdf"],
                      ["Game (USA).toc", "Game (USA).bin"], ["Game (Europe).cue", "Game (Europe).bin", "Game (Europe).sbi"],
                      ["Game.m3u", "Game (USA) (Disc 1).chd", "Game (USA) (Disc 2).chd"]):
            with self.subTest(files=files):
                self.assertTrue(discs.is_game_folder("Game (USA)", files))

    def test_generic_names(self):
        self.assertTrue(discs.is_game_folder("Saturn Game (USA)", ["game.iso"]))
        self.assertTrue(discs.is_game_folder("DC Game (USA)", ["disc.gdi", "track01.bin", "track02.raw"]))
        self.assertTrue(discs.is_game_folder("PC Game (USA)", ["Disc 1.cue", "Disc 1.bin", "PC Game (USA).txt"]))

    def test_extracted_discs_whatever_the_names(self):
        self.assertTrue(discs.is_game_folder("Demon's Souls (USA)", ["PS3_DISC.SFB"], ["PS3_GAME"]))
        self.assertTrue(discs.is_game_folder("BLUS30443", [], ["PS3_GAME"]))
        self.assertTrue(discs.is_game_folder("PS2 Game", ["SYSTEM.CNF", "SLUS_200.62"], ["DATA"]))
        self.assertTrue(discs.is_game_folder("PSP Game", ["UMD_DATA.BIN"], ["PSP_GAME"]))
        self.assertTrue(discs.is_game_folder("Halo", ["default.xbe", "maps.dat"]))

    def test_folders_of_many_games_are_not_game_folders(self):
        self.assertFalse(discs.is_game_folder("S", ["Snatcher (USA).cue", "Snatcher (USA).bin",
                                                    "Shining Force CD (USA).cue", "Shining Force CD (USA).bin"]))
        self.assertFalse(discs.is_game_folder("Q", ["Quake (USA).cue", "Quake (USA).bin"]))
        self.assertFalse(discs.is_game_folder("!Japan", ["Game (Japan).cue", "Game (Japan).bin"]))

    def test_files_of_one_game_in_a_folder_named_otherwise(self):
        self.assertTrue(discs.is_game_folder("Final Fantasy VII (USA)", ["FF7.CUE", "FF7.BIN"]))
        self.assertTrue(discs.is_game_folder("Sonic_CD", ["Sonic CD (USA).cue", "Sonic CD (USA) (Track 01).bin"]))

    def test_sort_folders_with_a_single_game_are_not_game_folders(self):
        for folder in ("Q", "q", "1-9", "!Homebrew", "!Japan", "!!BIOS"):
            with self.subTest(folder=folder):
                self.assertFalse(discs.is_game_folder(folder, ["Quake (USA).cue", "Quake (USA).bin"]))

    def test_folder_named_otherwise_with_subfolders_is_not_a_game_folder(self):
        self.assertFalse(discs.is_game_folder("PS1", ["Quake (USA).cue", "Quake (USA).bin"], ["Other Game (USA)"]))
        self.assertTrue(discs.is_game_folder("Quake (USA)", ["Quake (USA).cue", "Quake (USA).bin"], ["Extras"]))

    def test_folders_without_disc_hints_are_not_game_folders(self):
        self.assertFalse(discs.is_game_folder("Zelda (USA)", ["Zelda (USA).nes"]))
        self.assertFalse(discs.is_game_folder("Game (USA)", ["Game (USA).bin", "Game (USA).txt"]))
        self.assertFalse(discs.is_game_folder("Empty", []))

    def test_names_with_dots(self):
        self.assertTrue(discs.is_game_folder("Game Vol. 1 (USA)", ["Game Vol. 1 (USA).cue", "Game Vol. 1 (USA).bin"]))


class FindGameFoldersTest(unittest.TestCase):
    def test_finds_game_folders_at_any_depth(self):
        self.assertEqual(game_folders("Sonic CD (USA)/Sonic CD (USA).cue", "Sonic CD (USA)/Sonic CD (USA).bin",
                                      "PS3/Demon's Souls (USA)/PS3_DISC.SFB",
                                      "PS3/Demon's Souls (USA)/PS3_GAME/USRDIR/EBOOT.BIN",
                                      "Zelda (USA).nes", "N/NES Game (USA).nes"),
                         ["Sonic CD (USA)", os.path.join("PS3", "Demon's Souls (USA)")])

    def test_inner_game_folders_are_a_part_of_the_outer_one(self):
        self.assertEqual(game_folders("MGS (USA)/MGS (USA).m3u", "MGS (USA)/Disc 1/MGS (USA) (Disc 1).cue",
                                      "MGS (USA)/Disc 1/MGS (USA) (Disc 1).bin", "MGS (USA)/Disc 2/disc.gdi"),
                         ["MGS (USA)"])

    def test_root_is_never_a_game_folder(self):
        self.assertEqual(game_folders("Game (USA).cue", "Game (USA).bin", "SYSTEM.CNF"), [])


if __name__ == "__main__":
    unittest.main()
