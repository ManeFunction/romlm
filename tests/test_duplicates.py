import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import duplicates
from duplicates import Action
from tags import Release


def plan(*names):
    """Plans one game and returns the names of (kept, removed, tied) files."""
    result = duplicates.plan_group([Release.parse(n) for n in names], False)
    names_of = lambda releases: [r.name for r in releases]
    return (names_of(result.keep), names_of(result.remove) + names_of(result.betas_dropped), names_of(result.ties))


class PlanGroupTest(unittest.TestCase):
    def test_single_file_is_kept(self):
        self.assertEqual(plan("Game (USA).nes"), (["Game (USA).nes"], [], []))

    def test_usa_beats_europe_and_japan(self):
        keep, removed, ties = plan("Game (Japan).nes", "Game (Europe).nes", "Game (USA).nes")
        self.assertEqual((keep, ties), (["Game (USA).nes"], []))
        self.assertCountEqual(removed, ["Game (Japan).nes", "Game (Europe).nes"])

    def test_english_japanese_release_beats_plain_japanese(self):
        keep, _, _ = plan("Game (Japan).nes", "Game (Japan) (En).nes")
        self.assertEqual(keep, ["Game (Japan) (En).nes"])

    def test_later_revision_wins(self):
        keep, _, _ = plan("Game (USA) (Rev A).nes", "Game (USA) (Rev B).nes")
        self.assertEqual(keep, ["Game (USA) (Rev B).nes"])

    def test_v_prefixed_version_beats_unversioned(self):
        keep, _, _ = plan("Game (USA).nes", "Game (USA) (v1.1).nes")
        self.assertEqual(keep, ["Game (USA) (v1.1).nes"])

    def test_higher_version_wins(self):
        keep, _, _ = plan("Game (USA) (v1.2).nes", "Game (USA) (v1.10).nes")
        self.assertEqual(keep, ["Game (USA) (v1.10).nes"])

    def test_versioned_homebrew_beats_unversioned(self):
        keep, _, _ = plan("Hb (Homebrew).nes", "Hb (Homebrew) (v1.1).nes")
        self.assertEqual(keep, ["Hb (Homebrew) (v1.1).nes"])

    def test_implicit_homebrew_version_is_below_a_real_one(self):
        # The same amount of unknown tags on both sides, so only the version decides
        keep, _, _ = plan("Hb (Homebrew).nes", "Hb (Homebrew) (v1.1) (Extra).nes")
        self.assertEqual(keep, ["Hb (Homebrew) (v1.1) (Extra).nes"])

    def test_release_removes_all_betas(self):
        keep, removed, _ = plan("Game (USA) (Beta).nes", "Game (USA).nes", "Game (USA) (Proto).nes")
        self.assertEqual(keep, ["Game (USA).nes"])
        self.assertCountEqual(removed, ["Game (USA) (Beta).nes", "Game (USA) (Proto).nes"])

    def test_only_betas_keep_the_latest_dated_one(self):
        keep, removed, _ = plan("Game (USA) (Beta) (1993-07-09).nes", "Game (USA) (Beta) (1993-08-01).nes")
        self.assertEqual(keep, ["Game (USA) (Beta) (1993-08-01).nes"])
        self.assertEqual(removed, ["Game (USA) (Beta) (1993-07-09).nes"])

    def test_equal_betas_keep_the_first_one(self):
        keep, _, _ = plan("Game (USA) (Beta).nes", "Game (USA) (Beta).bin")
        self.assertEqual(keep, ["Game (USA) (Beta).nes"])

    def test_equally_good_releases_are_ties(self):
        keep, removed, ties = plan("Game (USA) (Foo).nes", "Game (USA) (Bar).nes")
        self.assertEqual((keep, removed), ([], []))
        self.assertCountEqual(ties, ["Game (USA) (Foo).nes", "Game (USA) (Bar).nes"])

    def test_empty_tags_do_not_crash(self):
        keep, _, _ = plan("Game ().nes", "Game (USA).nes")
        self.assertEqual(keep, ["Game (USA).nes"])
        plan("Game (v).nes", "Game (USA, ).nes")


class CleanDuplicatesTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def make(self, *names):
        paths = []
        for name in names:
            path = os.path.join(self.folder.name, name)
            open(path, "w").close()
            paths.append(path)
        return paths

    def left(self):
        return sorted(os.listdir(self.folder.name))

    def clean(self, paths, action=Action.KEEP_ALL, **effects):
        with contextlib.redirect_stdout(io.StringIO()):
            return duplicates.clean_duplicates(paths, action, True, False, **effects)

    def test_bios_files_are_never_removed(self):
        paths = self.make("[BIOS] Sega CD (USA).bin", "[BIOS] Sega CD (Europe).bin", "[BIOS] Saturn (USA).bin")
        self.assertEqual(self.clean(paths), paths)
        self.assertEqual(len(self.left()), 3)

    def test_removes_the_worse_files_and_returns_the_rest(self):
        paths = self.make("Game (Europe).nes", "Game (USA).nes", "Other (USA).nes")
        kept = self.clean(paths)
        self.assertEqual(self.left(), ["Game (USA).nes", "Other (USA).nes"])
        self.assertEqual([os.path.basename(p) for p in kept], ["Game (USA).nes", "Other (USA).nes"])

    def test_keep_all_keeps_the_tied_files(self):
        self.make("Game (USA) (Foo).nes", "Game (USA) (Bar).nes")
        self.clean([os.path.join(self.folder.name, n) for n in self.left()])
        self.assertEqual(len(self.left()), 2)

    def test_keep_one_keeps_the_first_by_name(self):
        paths = self.make("Game (USA) (Foo).nes", "Game (USA) (Bar).nes")
        self.clean(paths, Action.KEEP_ONE)
        self.assertEqual(self.left(), ["Game (USA) (Bar).nes"])

    def test_ask_keeps_the_chosen_file(self):
        paths = self.make("Game (USA) (Foo).nes", "Game (USA) (Bar).nes")
        # The tied files are offered in the order they were given: 1 is Foo, 2 is Bar
        asked = []
        def choose(candidates, number):
            asked.append([r.name for r in candidates])
            return candidates[1]
        self.clean(paths, Action.ASK, choose=choose)
        self.assertEqual(asked, [["Game (USA) (Foo).nes", "Game (USA) (Bar).nes"]])
        self.assertEqual(self.left(), ["Game (USA) (Bar).nes"])

    def test_ask_none_keeps_all(self):
        paths = self.make("Game (USA) (Foo).nes", "Game (USA) (Bar).nes")
        self.clean(paths, Action.ASK, choose=lambda candidates, number: None)
        self.assertEqual(len(self.left()), 2)

    def test_nothing_is_removed_before_all_the_questions_are_answered(self):
        paths = self.make("A (Europe).nes", "A (USA).nes", "B (USA) (Foo).nes", "B (USA) (Bar).nes")
        removed = []
        def interrupt(candidates, number):
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.clean(paths, Action.ASK, choose=interrupt, remove=removed.append)
        self.assertEqual(removed, [])
        self.assertEqual(len(self.left()), 4)

    def test_removes_through_the_given_function(self):
        paths = self.make("Game (Europe).nes", "Game (USA).nes")
        removed = []
        self.clean(paths, remove=removed.append)
        self.assertEqual([os.path.basename(p) for p in removed], ["Game (Europe).nes"])
        self.assertEqual(len(self.left()), 2)

    def test_ask_prompt_reads_a_number(self):
        releases = [Release.parse("Game (USA) (Foo).nes"), Release.parse("Game (USA) (Bar).nes")]
        with mock.patch("builtins.input", side_effect=["x", "9", "2"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertIs(duplicates.ask_which_to_keep(releases, ""), releases[1])
        with mock.patch("builtins.input", return_value="0"), contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(duplicates.ask_which_to_keep(releases, ""))

    def test_discs_of_one_game_are_kept(self):
        paths = self.make("Game (USA) (Disc 1).bin", "Game (USA) (Disc 2).bin", "Game (Europe) (Disc 1).bin")
        self.clean(paths)
        self.assertEqual(self.left(), ["Game (USA) (Disc 1).bin", "Game (USA) (Disc 2).bin"])


if __name__ == "__main__":
    unittest.main()
