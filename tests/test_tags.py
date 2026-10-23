import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tags import Release


class ReleaseParseTest(unittest.TestCase):
    def test_splits_name_and_tags(self):
        release = Release.parse("Roms/Game Name (USA, Europe) [!] (Rev A).nes")
        self.assertEqual(release.name, "Game Name (USA, Europe) [!] (Rev A).nes")
        self.assertEqual(release.base_name, "Game Name")
        self.assertEqual(release.tags, ("usa", "europe", "!", "rev a"))

    def test_name_without_tags(self):
        release = Release.parse("Game.nes")
        self.assertEqual(release.base_name, "Game")
        self.assertEqual(release.tags, ())

    def test_empty_tag_is_kept_as_empty_string(self):
        self.assertEqual(Release.parse("Game ().nes").tags, ("",))

    def test_each_disc_is_a_game_of_its_own(self):
        disc_1 = Release.parse("Game (USA) (Disc 1).bin")
        disc_2 = Release.parse("Game (Europe) (Disc 2).bin")
        self.assertEqual(disc_1.game_key, "game (disc 1)")
        self.assertNotEqual(disc_1.game_key, disc_2.game_key)

    def test_regions_do_not_split_a_game(self):
        self.assertEqual(Release.parse("Game (USA).nes").game_key, Release.parse("Game (Japan).nes").game_key)

    def test_case_does_not_split_a_game(self):
        self.assertEqual(Release.parse("Pac-Man (USA).nes").game_key, Release.parse("PAC-MAN (Japan).nes").game_key)
        self.assertEqual(Release.parse("Game (USA) (Disc 1).bin").game_key,
                         Release.parse("GAME (Japan) (DISC 1).bin").game_key)

    def test_bios(self):
        release = Release.parse("!!BIOS/[BIOS] Sega CD (USA).bin")
        self.assertTrue(release.is_bios)
        self.assertFalse(Release.parse("Sega CD (USA).bin").is_bios)

    def test_homebrew_and_pirates(self):
        self.assertTrue(Release.parse("Game (Homebrew).nes").is_homebrew)
        self.assertTrue(Release.parse("Game (Aftermarket).nes").is_homebrew)
        self.assertTrue(Release.parse("Game (Unl).nes").is_pirate)
        self.assertFalse(Release.parse("Game (USA).nes").is_pirate)

    def test_not_finished_releases_are_betas(self):
        for tag in ("Beta", "Beta 2", "Alpha", "Proto", "Sample", "Demo"):
            self.assertTrue(Release.parse(f"Game (USA) ({tag}).nes").is_beta, tag)
        self.assertFalse(Release.parse("Game (USA) (Rev A).nes").is_beta)


if __name__ == "__main__":
    unittest.main()
